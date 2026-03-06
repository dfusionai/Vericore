import time
import typing
import unicodedata
from dataclasses import dataclass
import bittensor as bt
import tldextract
import ipaddress
import re
import os
from urllib.parse import urlparse, parse_qs, unquote_plus

# python-Levenshtein required: without it, fuzz.partial_ratio uses a buggy pure-Python path
# that returns wrong low scores for short-vs-long (snippet vs page).
from fuzzywuzzy import fuzz

from shared.blacklisted_domain_cache import is_blacklisted_domain
from shared.exceptions import InsecureProtocolError
from shared.top_site_cache import is_approved_site
from shared.veridex_protocol import (
    SourceEvidence,
    SourceType,
    VericoreStatementResponse,
    FetchPageResult,
    StatementResponseTiming,
    SNIPPET_FETCHER_STATUS_NOT_RUN,
)
from validator.context_similarity_validator import calculate_similarity_score
from validator.domain_validator import domain_is_recently_registered
from validator.quality_model import score_statement_distribution
from validator.snippet_fetcher import fetch_entire_page
from validator.similarity_quality_model import verify_text_similarity, SENTENCE_SIMILARITY_THRESHOLD

from shared.debug_util import DEBUG_LOCAL

from shared.scores import (
    NO_SNIPPET_PROVIDED,
    SNIPPET_SAME_AS_STATEMENT,
    COULD_NOT_GET_PAGE_TEXT_FROM_URL,
    SNIPPET_NOT_VERIFIED_IN_URL,
    DOMAIN_REGISTERED_RECENTLY,
    SSL_DOMAIN_REQUIRED,
    APPROVED_URL_MULTIPLIER,
    EXCERPT_TOO_SIMILAR,
    USING_SEARCH_AS_EVIDENCE,
    UNRELATED_PAGE_SNIPPET,
    BLACKLISTED_URL_SCORE,
    INVALID_SNIPPET_EXCERPT,
    IS_SEARCH_WEB_PAGE,
    FAKE_SNIPPET,
    DESEARCH_EVIDENCE_NOT_IN_RESPONSE,
)
from validator.statement_context_evaluator import assess_statement_async
from validator.web_page_validator import is_search_web_page

MIN_SNIPPET_CONTEXT_SIMILARITY_SCORE = .65


@dataclass
class StatementExcerptCheckResult:
    """Result of _check_statement_excerpt. If early_exit_response is set, return it; else continue with is_similar_excerpt and statement_similarity_score."""
    early_exit_response: VericoreStatementResponse | None
    is_similar_excerpt: bool | None
    statement_similarity_score: float | None

# Snippet-in-page verification: fuzzy fallback when exact (normalized) match fails
FUZZY_VERIFY_THRESHOLD = 0.94  # ratio in [0, 1]; only accept if best match >= this (character-level tolerance only)
MIN_SNIPPET_LENGTH_FOR_FUZZY = 25  # minimum normalized snippet length to run fuzzy check (avoids trivial matches)

class SnippetValidator:

    def _extract_assessment_signals(self, assessment_result: dict) -> dict:
        """
        Extract the additional signals from assessment_result dict.
        Returns a dict with default values of 0.0 if signals are not present.
        """
        if not assessment_result:
            return {
                "sentiment": 0.0,
                "conviction": 0.0,
                "source_credibility": 0.0,
                "narrative_momentum": 0.0,
                "risk_reward_sentiment": 0.0,
                "catalyst_detection": 0.0,
                "political_leaning": 0.0
            }

        return {
            "sentiment": float(assessment_result.get("sentiment", 0.0)),
            "conviction": float(assessment_result.get("conviction", 0.0)),
            "source_credibility": float(assessment_result.get("source_credibility", 0.0)),
            "narrative_momentum": float(assessment_result.get("narrative_momentum", 0.0)),
            "risk_reward_sentiment": float(assessment_result.get("risk_reward_sentiment", 0.0)),
            "catalyst_detection": float(assessment_result.get("catalyst_detection", 0.0)),
            "political_leaning": float(assessment_result.get("political_leaning", 0.0))
        }

    def _extract_domain(self, url: str) -> str:
        parsed = urlparse(url)

        # Enforce "HTTPS" protocol
        if parsed.scheme.lower() != "https":
            raise InsecureProtocolError(url)

        hostname = parsed.hostname
        try:
            # Check if it's an IP address
            ipaddress.ip_address(hostname)
            return hostname  # Return as-is
        except ValueError:
            # It's not an IP, extract the domain
            ext = tldextract.extract(hostname)
            return f"{ext.domain}.{ext.suffix}" if ext.suffix else ext.domain

    def _extract_query_string(self, url: str) -> dict:
        parsed = urlparse(url)

        query_string = parsed.query

        return parse_qs(query_string)

    async def _fetch_page_text(self, request_id: str, miner_uid: int, url: str) -> FetchPageResult:
        """Returns FetchPageResult. On exception or empty result, returns a result with NOT_RUN statuses."""
        try:
            result = await fetch_entire_page(request_id, miner_uid, url)
            if result.cleaned_html is None:
                return FetchPageResult()
            return result
        except Exception as e:
            bt.logging.error(f"{request_id} | {miner_uid} | Error fetching page text in rendered page: {e}")
            return FetchPageResult()


    async def is_snippet_similar_to_statement(
        self, request_id: str, miner_uid: int, url: str, statement: str, snippet_text: str, similarity_threshold=SENTENCE_SIMILARITY_THRESHOLD
    ) :
        try:
            bt.logging.info(f"{request_id} | {miner_uid} | url: {url} | Checking whether the snippet provided is the same as the statement")
            return await verify_text_similarity(statement, snippet_text, similarity_threshold)

        except Exception as e:
            bt.logging.error(
                f"{request_id} | {miner_uid} | url: {url} | Error checking snippet similarity: {e}"
            )
            return False

    def write_file(self, request_id: str, page_text:str ):
        output_dir = "output/"
        os.makedirs(output_dir, exist_ok=True)
        filename = os.path.join(output_dir, f"{request_id}_{time.thread_time()}.txt")
        try:
            with open(filename, "w", encoding="utf-8") as f:
                f.write(page_text)
            bt.logging.info(f"********** DEBUG ****: Wrote page output file: {filename}")
        except Exception as e:
            bt.logging.error(f"********** DEBUG ****: Error writing page output file {filename}: {e}")

    async def _verify_snippet_in_rendered_page(
        self, request_id: str, miner_uid: int, page_text: str, snippet_text: str, url: str
    ) -> bool:
        try:
            def normalize_text(text):
                # Unicode normalization: same character, different bytes (e.g. quotes, accents, compatibility variants)
                text = unicodedata.normalize("NFKC", text or "")
                # Remove patterns like [ 1 ], [12], [ 123 ]
                text = re.sub(r"\[\s*\d+\s*\]", '', text)
                # Standardize quotes
                text = re.sub(r'["“”‘’`´]', "'", text)
                # Standardize dashes
                text = re.sub(r'[–—−]', '-', text)
                # Remove or standardize other punctuation (keep only alphanumerics, spaces, hyphens, and single quotes)
                text = re.sub(r"[^\w\s'-]", '', text)
                # Convert to lowercase
                text = text.lower()
                # Normalize whitespace: replace multiple spaces with a single space, strip leading/trailing
                text = re.sub(r'\s+', ' ', text).strip()
                return text

            try:
                normalized_snippet = normalize_text(snippet_text)
                normalized_page = normalize_text(page_text)
                if DEBUG_LOCAL:
                    bt.logging.info(f"{request_id} | {miner_uid} | {url} | Normalised text:{normalized_snippet}")
                    self.write_file(request_id, normalized_page)

                if normalized_snippet in normalized_page:
                    bt.logging.info(f"{request_id} | {miner_uid} | {url} | Web page is EXACTLY the same as the snippet (normalized).")
                    return True

                # Fuzzy fallback: same text with character-level differences only (no paraphrase)
                if len(normalized_snippet) >= MIN_SNIPPET_LENGTH_FOR_FUZZY and normalized_page:
                    # partial_ratio: best match of snippet against any substring of page (0-100)
                    ratio = fuzz.partial_ratio(normalized_snippet, normalized_page) / 100.0
                    if ratio >= FUZZY_VERIFY_THRESHOLD:
                        bt.logging.info(
                            f"{request_id} | {miner_uid} | {url} | Snippet verified via fuzzy match (ratio={ratio:.2f}, threshold={FUZZY_VERIFY_THRESHOLD})."
                        )
                        return True

                bt.logging.info(f"{request_id} | {miner_uid} | {url} | Web page is NOT exactly the same as the snippet (normalized)")
                return False
            except Exception as e:
                bt.logging.error(
                    f"{request_id} | {miner_uid} | {url} | Error verifying snippet in rendered page: {e}"
                )
                return False
        except Exception as e:
            bt.logging.error(
                f"{request_id} | {miner_uid} | {url} | Error verifying snippet in rendered page: {e}"
            )
            return False

    def get_last_meaningful_url_part(self, url: str):
        parsed = urlparse(url)
        path_parts = [part for part in parsed.path.split('/') if part]
        if not path_parts:
            return ''
        return unquote_plus(path_parts[-1])

    async def validate_miner_query_params(
        self,
        request_id: str,
        miner_uid: int,
        domain: str,
        original_statement: str,
        miner_evidence: SourceEvidence
    ):
        query_params = self._extract_query_string(miner_evidence.url)
        if query_params is None:
            return None

        # check whether query params is the same as the excerpt
        for key, values in query_params.items():
            bt.logging.info(f"{request_id} | {miner_uid} | {miner_evidence.url} | {values[0]} | {miner_evidence.excerpt} | Checking query parameters")

            is_similar_excerpt, statement_similarity_score,  = await self.is_snippet_similar_to_statement(
                request_id, miner_uid, miner_evidence.url, miner_evidence.excerpt, values[0]
            )

            bt.logging.info(f"{request_id} | {miner_uid} | {miner_evidence.url} | {values[0]} | {miner_evidence.excerpt} | Is similar to query parameter: {is_similar_excerpt}, {statement_similarity_score}")

            # Using search as evidence - 5
            if is_similar_excerpt:
                bt.logging.info(f"{request_id} | {miner_uid} | {miner_evidence.url} | {values[0]} | Query Parameter Excerpt is the SAME")
                return self._create_invalid_statement_response(
                    miner_evidence, domain, USING_SEARCH_AS_EVIDENCE,
                    f"query_parameter_same_as_evidence ({statement_similarity_score})",
                )

        parsed = urlparse(miner_evidence.url)
        path_parts = [unquote_plus(part.strip()) for part in parsed.path.split('/') if part]

        for part_index, part in enumerate(path_parts):
            if part.lower() == "search":
            # if re.search(r"[\\/]*search[\\/]*", part):
                bt.logging.info(f"{request_id} | {miner_uid} | {miner_evidence.url} | {part} | search is part of url")
                return self._create_invalid_statement_response(
                    miner_evidence, domain, USING_SEARCH_AS_EVIDENCE, "using_search_in_url_as_evidence"
                )

            if part_index == len(path_parts) - 1:
                word_count = len(part.split())
                # has_punctuation = bool(re.search(r"[.,:;!?]", decoded_part))

                if word_count > 3:
                    bt.logging.info(f"{request_id} | {miner_uid} | {miner_evidence.url} | {part} | Last url search parameter is sentence")
                    return self._create_invalid_statement_response(
                        miner_evidence, domain, USING_SEARCH_AS_EVIDENCE, "using_search_as_part_of_url"
                    )

                if "%20" in part:
                    bt.logging.info(f"{request_id} | {miner_uid} | {miner_evidence.url} | {part} | Last url search parameter is sentence:%20 ")
                    return self._create_invalid_statement_response(
                        miner_evidence, domain, USING_SEARCH_AS_EVIDENCE, "using_search_as_evidence:%20"
                    )

                is_similar_excerpt, statement_similarity_score,  = await self.is_snippet_similar_to_statement(
                    request_id, miner_uid, miner_evidence.url, miner_evidence.excerpt, part
                )
                if is_similar_excerpt:
                    bt.logging.info(f"{request_id} | {miner_uid} | {miner_evidence.url} | {part} | Excerpt is same as url")
                    return self._create_invalid_statement_response(
                        miner_evidence, domain, USING_SEARCH_AS_EVIDENCE, "excerpt_is_same_as_url"
                    )

        # llm_response = await assess_url_as_fake(
        #     request_id,
        #     miner_uid,
        #     miner_evidence.url,
        #     original_statement,
        #     miner_evidence.excerpt
        # )
        #
        # if llm_response is not None and llm_response.get("response") == "FAKE":
        #     bt.logging.info(f"{request_id} | {miner_uid} | {miner_evidence.url} | FAKE Url detected by LLM")
        #     snippet_score = FAKE_MINER_URL
        #     vericore_miner_response = VericoreStatementResponse(
        #         url=miner_evidence.url,
        #         excerpt=miner_evidence.excerpt,
        #         domain=domain,
        #         snippet_found=False,
        #         local_score=0.0,
        #         snippet_score=snippet_score,
        #         snippet_score_reason="fake_url_response",
        #     )
        #     return vericore_miner_response

    # Validates provided miner url
    async def validate_miner_url(
        self,
        request_id: str,
        miner_uid: int,
        original_statement: str,
        domain: str,
        miner_evidence: SourceEvidence
    ) -> VericoreStatementResponse | None:

        # Check if domain is blacklisted
        if is_blacklisted_domain(request_id=request_id, miner_uid=miner_uid, domain=domain):
            return self._create_invalid_statement_response(
                miner_evidence, domain, BLACKLISTED_URL_SCORE, "blacklisted_url"
            )

        # check if url has query string and excerpt same as query string
        response = await self.validate_miner_query_params(
            request_id,
            miner_uid,
            domain,
            original_statement,
            miner_evidence
        )

        if response is not None:
            return response

        # Dont score if domain was registered within 30 days.
        domain_registered_recently = await domain_is_recently_registered(domain)

        bt.logging.info(
            f"{request_id} | {miner_uid} | {miner_evidence.url} | Is domain registered recently: {domain_registered_recently}"
        )
        if domain_registered_recently:
            return self._create_invalid_statement_response(
                miner_evidence, domain, DOMAIN_REGISTERED_RECENTLY, "domain_is_recently_registered"
            )

    def is_valid_separator_sentence(self, sentence):
        if not sentence:
            return False
        #
        # sentence = sentence.replace('’', "'").replace('“', '"').replace('”', '"').replace('–', '-').replace('—', '-')
        #
        # # Must start with an alphanumeric character
        # if not sentence[0].isalnum():
        #     return False
        #
        # # Must end with an alphanumeric character or valid punctuation
        # # if not re.search(r'[A-Za-z0-9]$|(\.\.\.|[.!?])$', sentence):
        # #     return False

        # Must contain at least two words
        number_of_words = sentence.strip().split()
        if len(number_of_words) < 5:
            return False

        # check if there is
        return True

        #
        # # Accept common scientific characters in words
        # allowed_special_chars = set(".,:^∙()/-×%—'")
        #
        # for word in words:
        #     clean = re.sub(r'[.!?]+$', '', word)  # remove trailing punctuation
        #     specials = [ch for ch in clean if not ch.isalnum() and ch not in allowed_special_chars]
        #
        #     if len(specials) > 0:  # Fail only if *unexpected* specials are found
        #         return False
        #
        return True

    def _evidence_in_desearch_response(
        self, url: str, excerpt: str, response_body: bytes
    ) -> bool:
        """Check if url is present in the Desearch response body (text or JSON). Excerpt is not checked."""
        try:
            if response_body is None:
                return False
            text = response_body.decode("utf-8", errors="replace") or ""
            if url and url not in text:
                return False
            return True
        except Exception:
            return False

    async def _run_assess_statement(
        self,
        request_id: str,
        miner_uid: int,
        statement_url: str,
        statement: str,
        webpage: str,
        miner_excerpt: str,
    ) -> tuple[dict | None, float]:
        """Run AI statement assessment. Returns (assessment_result, time_taken_secs). Reusable for web and desearch."""
        start = time.perf_counter()
        result = await assess_statement_async(
            request_id=request_id,
            miner_uid=miner_uid,
            statement_url=statement_url,
            statement=statement,
            webpage=webpage,
            miner_excerpt=miner_excerpt,
        )
        return result, time.perf_counter() - start

    def _with_verify_time(
        self,
        response: VericoreStatementResponse,
        start_time: float,
    ) -> VericoreStatementResponse:
        """Set verify_miner_time_taken_secs on response (and timing) from start_time. Always set regardless of snippet_found."""
        elapsed = time.perf_counter() - start_time
        response.verify_miner_time_taken_secs = elapsed
        if response.timing is not None:
            response.timing.verify_miner_time_taken_secs = elapsed
        return response

    def _create_invalid_statement_response(
        self,
        miner_evidence: SourceEvidence,
        domain: str,
        snippet_score: float,
        snippet_score_reason: str,
        **kwargs,
    ) -> VericoreStatementResponse:
        """Build an invalid VericoreStatementResponse (snippet_found=False, verify_miner_time_taken_secs=0). Pass any extra fields via kwargs."""
        return VericoreStatementResponse(
            url=miner_evidence.url,
            excerpt=miner_evidence.excerpt,
            domain=domain,
            snippet_found=False,
            local_score=0.0,
            snippet_score=snippet_score,
            snippet_score_reason=snippet_score_reason,
            verify_miner_time_taken_secs=0,
            timing=StatementResponseTiming(verify_miner_time_taken_secs=0),
            **kwargs,
        )

    async def _check_statement_excerpt(
        self,
        request_id: str,
        miner_uid: int,
        original_statement: str,
        miner_evidence: SourceEvidence,
        domain: str,
        check_excerpt_similarity: bool = True,
    ) -> StatementExcerptCheckResult:
        """
        Shared excerpt checks: empty snippet, same-as-statement, invalid sentence.
        If check_excerpt_similarity is True (web), also runs excerpt-too-similar check.
        Desearch uses check_excerpt_similarity=False. Returns a StatementExcerptCheckResult;
        when early_exit_response is set, return it; otherwise continue with the similarity fields.
        verify_miner_time_taken_secs is left 0; caller sets it before returning if needed.
        """
        snippet_str = miner_evidence.excerpt.strip()

        if not snippet_str:
            return StatementExcerptCheckResult(
                early_exit_response=self._create_invalid_statement_response(
                    miner_evidence, domain, NO_SNIPPET_PROVIDED, "no_snippet_provided"
                ),
                is_similar_excerpt=None,
                statement_similarity_score=None,
            )

        if snippet_str == original_statement.strip():
            return StatementExcerptCheckResult(
                early_exit_response=self._create_invalid_statement_response(
                    miner_evidence, domain, SNIPPET_SAME_AS_STATEMENT, "snippet_same_as_statement"
                ),
                is_similar_excerpt=None,
                statement_similarity_score=None,
            )

        if not self.is_valid_separator_sentence(snippet_str):
            return StatementExcerptCheckResult(
                early_exit_response=self._create_invalid_statement_response(
                    miner_evidence, domain, INVALID_SNIPPET_EXCERPT, "invalid_excerpt"
                ),
                is_similar_excerpt=None,
                statement_similarity_score=None,
            )

        if not check_excerpt_similarity:
            return StatementExcerptCheckResult(early_exit_response=None, is_similar_excerpt=False, statement_similarity_score=0.0)

        bt.logging.info(
            f"{request_id} | {miner_uid} | {miner_evidence.url} | Is snippet in same context as statement"
        )
        is_similar_excerpt, statement_similarity_score = await self.is_snippet_similar_to_statement(
            request_id, miner_uid, miner_evidence.url, original_statement, snippet_str
        )
        bt.logging.info(
            f"{request_id} | {miner_uid} | {miner_evidence.url} | Is the same statement: {is_similar_excerpt} | Snippet Context: {statement_similarity_score}"
        )

        if is_similar_excerpt:
            return StatementExcerptCheckResult(
                early_exit_response=self._create_invalid_statement_response(
                    miner_evidence, domain, EXCERPT_TOO_SIMILAR, "excerpt_too_similar",
                    statement_similarity_score=statement_similarity_score,
                ),
                is_similar_excerpt=is_similar_excerpt,
                statement_similarity_score=statement_similarity_score,
            )

        return StatementExcerptCheckResult(
            early_exit_response=None,
            is_similar_excerpt=is_similar_excerpt,
            statement_similarity_score=statement_similarity_score,
        )

    async def _validate_desearch_snippet(
        self,
        request_id: str,
        miner_uid: int,
        original_statement: str,
        miner_evidence: SourceEvidence,
        bodies: typing.Sequence[bytes],
    ) -> VericoreStatementResponse:
        """Validate a snippet with source_type desearch: evidence-in-body only; no statement/excerpt or similarity validation (desearch assumed valid). NLI and assessment for signals. verify_miner_time_taken_secs set by caller on success."""
        bodies = bodies or ()
        if not bodies or not any(
            self._evidence_in_desearch_response(miner_evidence.url, miner_evidence.excerpt, body)
            for body in bodies
        ):
            return self._create_invalid_statement_response(
                miner_evidence, "", DESEARCH_EVIDENCE_NOT_IN_RESPONSE, "desearch_evidence_not_in_response"
            )

        try:
            domain = self._extract_domain(miner_evidence.url)
        except InsecureProtocolError:
            bt.logging.error(f"{request_id} | {miner_uid} | {miner_evidence.url} | Url provided isn't SSL")
            return self._create_invalid_statement_response(
                miner_evidence, "", SSL_DOMAIN_REQUIRED, "ssl_url_required"
            )            
        except Exception:
            domain = ""

        # Desearch evidence is assumed valid; skip statement/excerpt and similarity validation.

        probs, local_score = await score_statement_distribution(
            statement=original_statement.strip(),
            snippet=miner_evidence.excerpt,
        )

        assessment_result, assess_statement_time_taken_secs = await self._run_assess_statement(
            request_id=request_id,
            miner_uid=miner_uid,
            statement_url=miner_evidence.url,
            statement=original_statement,
            webpage=miner_evidence.excerpt,
            miner_excerpt=miner_evidence.excerpt,
        )
        signals = self._extract_assessment_signals(assessment_result) if assessment_result else self._extract_assessment_signals({})

        bt.logging.info(
            f"{request_id} | {miner_uid} | {miner_evidence.url} | Desearch snippet validated | "
            f"local_score: {local_score} | assess_secs: {assess_statement_time_taken_secs:.3f}s"
        )
        return VericoreStatementResponse(
            url=miner_evidence.url,
            excerpt=miner_evidence.excerpt,
            domain=domain,
            snippet_found=True,
            domain_factor=0,
            contradiction=probs["contradiction"],
            neutral=probs["neutral"],
            entailment=probs["entailment"],
            local_score=local_score,
            approved_url_multiplier=1,
            snippet_score=0,
            context_similarity_score=0.0,
            statement_similarity_score=0.0,
            is_similar_context=False,
            assessment_result=assessment_result or {},
            sentiment=signals["sentiment"],
            conviction=signals["conviction"],
            source_credibility=signals["source_credibility"],
            narrative_momentum=signals["narrative_momentum"],
            risk_reward_sentiment=signals["risk_reward_sentiment"],
            catalyst_detection=signals["catalyst_detection"],
            political_leaning=signals["political_leaning"],
            verify_miner_time_taken_secs=0,
            assess_statement_time_taken_secs=assess_statement_time_taken_secs,
            timing=StatementResponseTiming(
                verify_miner_time_taken_secs=0,
                assess_statement_time_taken_secs=assess_statement_time_taken_secs,
            ),
        )

    async def validate_miner_snippet(
        self,
        request_id: str,
        miner_uid: int,
        original_statement: str,
        miner_evidence: SourceEvidence,
        desearch_response_bodies: typing.Sequence[bytes] | None = None,
    ) -> VericoreStatementResponse:
        start_time = time.perf_counter()
        bodies = desearch_response_bodies or ()

        bt.logging.info(
            f"{request_id} | {miner_uid} | {miner_evidence.url} | Verifying miner snippet"
        )
        try:
            source_type_str = getattr(miner_evidence, "source_type", SourceType.WEB.value)
            is_desearch = source_type_str == SourceType.DESEARCH.value

            if is_desearch:
                resp = await self._validate_desearch_snippet(
                    request_id, miner_uid, original_statement, miner_evidence, bodies
                )
                return self._with_verify_time(resp, start_time)

            resp = await self._validate_web_snippet(
                request_id, miner_uid, original_statement, miner_evidence
            )
            return self._with_verify_time(resp, start_time)
        except Exception as e:
            bt.logging.error(
                f"{request_id} | {miner_uid} | Error fetching miner snippet {e}"
            )
            return self._create_invalid_statement_response(
                miner_evidence, "", -1.0, "error_verifying_miner_snippet"
            )

    async def _validate_web_snippet(
        self,
        request_id: str,
        miner_uid: int,
        original_statement: str,
        miner_evidence: SourceEvidence,
    ) -> VericoreStatementResponse:
        """Validate a snippet with source_type web: domain/URL checks, page fetch, snippet-in-page verify, assessment, NLI. verify_miner_time_taken_secs set by caller on success."""
        start_time = time.perf_counter()
        try:
            domain = self._extract_domain(miner_evidence.url)
        except InsecureProtocolError:
            bt.logging.error(f"{request_id} | {miner_uid} | {miner_evidence.url} | Url provided isn't SSL")
            return self._create_invalid_statement_response(
                miner_evidence, "", SSL_DOMAIN_REQUIRED, "ssl_url_required"
            )

        bt.logging.info(
            f"{request_id} | {miner_uid} | {miner_evidence.url} | Domain verified"
        )

        vericore_miner_response = await self.validate_miner_url(
            request_id=request_id,
            miner_uid=miner_uid,
            original_statement=original_statement,
            domain=domain,
            miner_evidence=miner_evidence
        )
        if vericore_miner_response is not None:
            return vericore_miner_response

        # check if snippet comes from verified domain
        approved_url_multiplier = 1
        if is_approved_site(request_id, miner_uid, domain):
            approved_url_multiplier = APPROVED_URL_MULTIPLIER

        bt.logging.info(
            f"{request_id} | {miner_uid} | {miner_evidence.url} | Validating snippet"
        )

        excerpt_check = await self._check_statement_excerpt(
            request_id, miner_uid, original_statement, miner_evidence, domain
        )
        if excerpt_check.early_exit_response is not None:
            return excerpt_check.early_exit_response

        snippet_str = miner_evidence.excerpt.strip()

        bt.logging.info(
            f"{request_id} | {miner_uid} | {miner_evidence.url} | Fetching page text"
        )

        # Fetch page text
        fetch_page_start_time = time.perf_counter()
        fetch_result = await self._fetch_page_text(request_id, miner_uid, miner_evidence.url)
        fetch_page_time_taken_secs = time.perf_counter() - fetch_page_start_time
        page_text = fetch_result.cleaned_html or ""
        http_secs, selenium_secs, total_secs = self._snippet_fetcher_times(
            fetch_result.fetch_by_http_time_secs, fetch_result.fetch_by_selenium_time_secs
        )

        # Could not extract page text from url
        if not page_text:
            snippet_score = COULD_NOT_GET_PAGE_TEXT_FROM_URL
            vericore_miner_response = VericoreStatementResponse(
                url=miner_evidence.url,
                excerpt=miner_evidence.excerpt,
                domain=domain,
                snippet_found=False,
                local_score=0.0,
                snippet_score=snippet_score,
                snippet_score_reason="could_not_extract_html_from_url",
                verify_miner_time_taken_secs=0,
                fetch_page_time_taken_secs=fetch_page_time_taken_secs,
                snippet_fetcher_http_time_secs=http_secs,
                snippet_fetcher_selenium_time_secs=selenium_secs,
                snippet_fetcher_total_time_secs=total_secs,
                cleaning_html_time_taken_secs=fetch_result.cleaning_html_time_secs,
                fetch_by_http_status=fetch_result.fetch_by_http_status,
                fetch_by_selenium_status=fetch_result.fetch_by_selenium_status,
                timing=self._make_statement_timing(
                    0, fetch_page_time_taken_secs, 0.0,
                    http_secs, selenium_secs, total_secs,
                    fetch_result.cleaning_html_time_secs,
                    fetch_result.fetch_by_http_status, fetch_result.fetch_by_selenium_status,
                ),
            )
            return vericore_miner_response

        if is_search_web_page(page_text):
            snippet_score = IS_SEARCH_WEB_PAGE
            return VericoreStatementResponse(
                url=miner_evidence.url,
                excerpt=miner_evidence.excerpt,
                domain=domain,
                snippet_found=False,
                local_score=0.0,
                snippet_score=snippet_score,
                snippet_score_reason="is_search_web_page",
                verify_miner_time_taken_secs=0,
                fetch_page_time_taken_secs=fetch_page_time_taken_secs,
                snippet_fetcher_http_time_secs=http_secs,
                snippet_fetcher_selenium_time_secs=selenium_secs,
                snippet_fetcher_total_time_secs=total_secs,
                cleaning_html_time_taken_secs=fetch_result.cleaning_html_time_secs,
                fetch_by_http_status=fetch_result.fetch_by_http_status,
                fetch_by_selenium_status=fetch_result.fetch_by_selenium_status,
                timing=self._make_statement_timing(
                    0, fetch_page_time_taken_secs, 0.0,
                    http_secs, selenium_secs, total_secs,
                    fetch_result.cleaning_html_time_secs,
                    fetch_result.fetch_by_http_status, fetch_result.fetch_by_selenium_status,
                ),
            )

        bt.logging.info(
            f"{request_id} | {miner_uid} | {miner_evidence.url} | Verifying snippet in rendered page"
        )

        assessment_result, assess_statement_time_taken_secs = await self._run_assess_statement(
            request_id=request_id,
            miner_uid=miner_uid,
            statement_url=miner_evidence.url,
            statement=original_statement,
            webpage=page_text,
            miner_excerpt=miner_evidence.excerpt,
        )

        bt.logging.info(
            f"{request_id} | {miner_uid} | {miner_evidence.url} | Assessment Result: {assessment_result}"
        )
        if assessment_result is not None:
            snippet_result = assessment_result.get("snippet_status")
            is_search_url = assessment_result.get("is_search_url")

            if snippet_result == "UNRELATED":
                snippet_score = UNRELATED_PAGE_SNIPPET
                return VericoreStatementResponse(
                    url=miner_evidence.url,
                    excerpt=miner_evidence.excerpt,
                    domain=domain,
                    snippet_found=False,
                    local_score=0.0,
                    snippet_score=snippet_score,
                    snippet_score_reason="unrelated_page_snippet",
                    rejection_reason = assessment_result.get("reason"),
                    assessment_result = assessment_result,
                    verify_miner_time_taken_secs=0,
                    fetch_page_time_taken_secs=fetch_page_time_taken_secs,
                    assess_statement_time_taken_secs=assess_statement_time_taken_secs,
                    snippet_fetcher_http_time_secs=http_secs,
                    snippet_fetcher_selenium_time_secs=selenium_secs,
                    snippet_fetcher_total_time_secs=total_secs,
                    cleaning_html_time_taken_secs=fetch_result.cleaning_html_time_secs,
                    fetch_by_http_status=fetch_result.fetch_by_http_status,
                    fetch_by_selenium_status=fetch_result.fetch_by_selenium_status,
                    timing=self._make_statement_timing(
                        0, fetch_page_time_taken_secs, assess_statement_time_taken_secs,
                        http_secs, selenium_secs, total_secs,
                        fetch_result.cleaning_html_time_secs,
                        fetch_result.fetch_by_http_status, fetch_result.fetch_by_selenium_status,
                    ),
                )
            elif snippet_result == "FAKE":
                snippet_score = FAKE_SNIPPET
                return VericoreStatementResponse(
                    url=miner_evidence.url,
                    excerpt=miner_evidence.excerpt,
                    domain=domain,
                    snippet_found=False,
                    local_score=0.0,
                    snippet_score=snippet_score,
                    snippet_score_reason="fake_page_snippet",
                    assessment_result=assessment_result,
                    rejection_reason = assessment_result.get("reason"),
                    verify_miner_time_taken_secs=0,
                    fetch_page_time_taken_secs=fetch_page_time_taken_secs,
                    assess_statement_time_taken_secs=assess_statement_time_taken_secs,
                    snippet_fetcher_http_time_secs=http_secs,
                    snippet_fetcher_selenium_time_secs=selenium_secs,
                    snippet_fetcher_total_time_secs=total_secs,
                    cleaning_html_time_taken_secs=fetch_result.cleaning_html_time_secs,
                    fetch_by_http_status=fetch_result.fetch_by_http_status,
                    fetch_by_selenium_status=fetch_result.fetch_by_selenium_status,
                    timing=self._make_statement_timing(
                        0, fetch_page_time_taken_secs, assess_statement_time_taken_secs,
                        http_secs, selenium_secs, total_secs,
                        fetch_result.cleaning_html_time_secs,
                        fetch_result.fetch_by_http_status, fetch_result.fetch_by_selenium_status,
                    ),
                )
            elif is_search_url:
                snippet_score = IS_SEARCH_WEB_PAGE
                return VericoreStatementResponse(
                    url=miner_evidence.url,
                    excerpt=miner_evidence.excerpt,
                    domain=domain,
                    snippet_found=False,
                    local_score=0.0,
                    snippet_score=snippet_score,
                    assessment_result=assessment_result,
                    snippet_score_reason="is_search_web_page",
                    rejection_reason = assessment_result.get("reason"),
                    verify_miner_time_taken_secs=0,
                    fetch_page_time_taken_secs=fetch_page_time_taken_secs,
                    assess_statement_time_taken_secs=assess_statement_time_taken_secs,
                    snippet_fetcher_http_time_secs=http_secs,
                    snippet_fetcher_selenium_time_secs=selenium_secs,
                    snippet_fetcher_total_time_secs=total_secs,
                    cleaning_html_time_taken_secs=fetch_result.cleaning_html_time_secs,
                    fetch_by_http_status=fetch_result.fetch_by_http_status,
                    fetch_by_selenium_status=fetch_result.fetch_by_selenium_status,
                    timing=self._make_statement_timing(
                        0, fetch_page_time_taken_secs, assess_statement_time_taken_secs,
                        http_secs, selenium_secs, total_secs,
                        fetch_result.cleaning_html_time_secs,
                        fetch_result.fetch_by_http_status, fetch_result.fetch_by_selenium_status,
                    ),
                )

        # Verify that the snippet is actually within the provided url
        # #todo - should we split score between url exists and whether the web-page does include the snippet
        snippet_found = await self._verify_snippet_in_rendered_page(
            request_id, miner_uid, page_text, snippet_str, miner_evidence.url
        )

        bt.logging.info(
            f"{request_id} | {miner_uid} | {miner_evidence.url} | Snippet Verified: {snippet_found}"
        )

        # Snippet was not found from the provided url:
        if not snippet_found:
            snippet_score = SNIPPET_NOT_VERIFIED_IN_URL
            vericore_miner_response = VericoreStatementResponse(
                url=miner_evidence.url,
                excerpt=miner_evidence.excerpt,
                domain=domain,
                snippet_found=False,
                local_score=0.0,
                snippet_score=snippet_score,
                snippet_score_reason="snippet_not_verified_in_url",
                assessment_result=assessment_result,
                page_text=page_text if DEBUG_LOCAL else "",
                verify_miner_time_taken_secs=0,
                fetch_page_time_taken_secs=fetch_page_time_taken_secs,
                assess_statement_time_taken_secs=assess_statement_time_taken_secs,
                snippet_fetcher_http_time_secs=http_secs,
                snippet_fetcher_selenium_time_secs=selenium_secs,
                snippet_fetcher_total_time_secs=total_secs,
                cleaning_html_time_taken_secs=fetch_result.cleaning_html_time_secs,
                fetch_by_http_status=fetch_result.fetch_by_http_status,
                fetch_by_selenium_status=fetch_result.fetch_by_selenium_status,
                timing=self._make_statement_timing(
                    0, fetch_page_time_taken_secs, assess_statement_time_taken_secs,
                    http_secs, selenium_secs, total_secs,
                    fetch_result.cleaning_html_time_secs,
                    fetch_result.fetch_by_http_status, fetch_result.fetch_by_selenium_status,
                ),
            )
            return vericore_miner_response

        context_similarity_score = calculate_similarity_score(
            statement=original_statement.strip(),
            excerpt=miner_evidence.excerpt
        )

        bt.logging.info(
            f"{request_id} | {miner_uid} | {miner_evidence.url} | Context similarity: {context_similarity_score} "
        )

        # Taken out for now since AI is checking context similarity - which is a better option
        # # Zero score if excerpt isn't context similar to statement
        # if context_similarity_score < MIN_SNIPPET_CONTEXT_SIMILARITY_SCORE:
        #     snippet_score = SNIPPET_NOT_CONTEXT_SIMILAR
        #     return VericoreStatementResponse(
        #         url=miner_evidence.url,
        #         excerpt=miner_evidence.excerpt,
        #         domain=domain,
        #         snippet_found=False,
        #         local_score=0.0,
        #         snippet_score=snippet_score,
        #         snippet_score_reason="snippet_not_context_similar",
        #         context_similarity_score=context_similarity_score,
        #         assessment_result=assessment_result,
        #         page_text=""
        #     )

        # Determine whether statement is neutral/corroborated or refuted
        probs, local_score = await score_statement_distribution(
            statement=original_statement.strip(),
            snippet=miner_evidence.excerpt
        )

        end_time = time.perf_counter()
        signals = self._extract_assessment_signals(assessment_result) if assessment_result else self._extract_assessment_signals({})
        total_time = end_time - start_time
        vericore_miner_response = VericoreStatementResponse(
            url=miner_evidence.url,
            excerpt=miner_evidence.excerpt,
            domain=domain,
            snippet_found=True,
            domain_factor=0,
            contradiction=probs["contradiction"],
            neutral=probs["neutral"],
            entailment=probs["entailment"],
            local_score=local_score,
            approved_url_multiplier=approved_url_multiplier,
            snippet_score=0,
            context_similarity_score=context_similarity_score,
            statement_similarity_score=excerpt_check.statement_similarity_score,
            is_similar_context=excerpt_check.is_similar_excerpt,
            assessment_result=assessment_result,
            sentiment=signals["sentiment"],
            conviction=signals["conviction"],
            source_credibility=signals["source_credibility"],
            narrative_momentum=signals["narrative_momentum"],
            risk_reward_sentiment=signals["risk_reward_sentiment"],
            catalyst_detection=signals["catalyst_detection"],
            political_leaning=signals["political_leaning"],
            verify_miner_time_taken_secs=0,
            fetch_page_time_taken_secs=fetch_page_time_taken_secs,
            assess_statement_time_taken_secs=assess_statement_time_taken_secs,
            snippet_fetcher_http_time_secs=http_secs,
            snippet_fetcher_selenium_time_secs=selenium_secs,
            snippet_fetcher_total_time_secs=total_secs,
            cleaning_html_time_taken_secs=fetch_result.cleaning_html_time_secs,
            fetch_by_http_status=fetch_result.fetch_by_http_status,
            fetch_by_selenium_status=fetch_result.fetch_by_selenium_status,
            timing=self._make_statement_timing(
                0, fetch_page_time_taken_secs, assess_statement_time_taken_secs,
                http_secs, selenium_secs, total_secs,
                fetch_result.cleaning_html_time_secs,
                fetch_result.fetch_by_http_status, fetch_result.fetch_by_selenium_status,
            ),
        )
        other_time = total_time - fetch_page_time_taken_secs - assess_statement_time_taken_secs
        bt.logging.info(
            f"{request_id} | {miner_uid} | {miner_evidence.url} | Finished verifying miner snippet | "
            f"Total: {total_time:.3f}s | Fetch: {fetch_page_time_taken_secs:.3f}s | AI: {assess_statement_time_taken_secs:.3f}s | Other: {other_time:.3f}s"
        )

        return vericore_miner_response

    @staticmethod
    def _snippet_fetcher_times(http_secs: float, selenium_secs: float) -> tuple[float, float, float]:
        """Compute total_secs from fetch_by_http_time_secs and fetch_by_selenium_time_secs (already float, -1 if NA). Returns (http_secs, selenium_secs, total_secs)."""
        total_secs = -1.0
        if http_secs >= 0 and selenium_secs >= 0:
            total_secs = http_secs + selenium_secs
        elif http_secs >= 0:
            total_secs = http_secs
        elif selenium_secs >= 0:
            total_secs = selenium_secs
        return http_secs, selenium_secs, total_secs

    def _make_statement_timing(
        self,
        verify_secs: float,
        fetch_page_secs: float,
        assess_secs: float,
        http_secs: float,
        selenium_secs: float,
        total_secs: float,
        cleaning_secs: float,
        http_status: str,
        selenium_status: str,
    ) -> StatementResponseTiming:
        """Build StatementResponseTiming for web snippet responses. Reusable for consistent timing shape."""
        return StatementResponseTiming(
            verify_miner_time_taken_secs=verify_secs,
            fetch_page_time_taken_secs=fetch_page_secs,
            assess_statement_time_taken_secs=assess_secs,
            fetch_by_http_time_secs=http_secs,
            fetch_by_selenium_time_secs=selenium_secs,
            snippet_fetcher_total_time_secs=total_secs,
            cleaning_html_time_taken_secs=cleaning_secs,
            fetch_by_http_status=http_status,
            fetch_by_selenium_status=selenium_status,
        )


validator = SnippetValidator()

async def run_validate_miner_snippet(
    request_id: str,
    miner_uid: int,
    original_statement: str,
    miner_evidence: SourceEvidence,
    desearch_response_bodies: typing.Sequence[bytes] | None = None,
) -> VericoreStatementResponse:
    return await validator.validate_miner_snippet(
        request_id,
        miner_uid,
        original_statement,
        miner_evidence,
        desearch_response_bodies=desearch_response_bodies,
    )
