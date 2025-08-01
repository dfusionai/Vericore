import time
import bittensor as bt
import tldextract
import ipaddress
import re
import os
from urllib.parse import urlparse, parse_qs, unquote_plus

from shared.blacklisted_domain_cache import is_blacklisted_domain
from shared.exceptions import InsecureProtocolError
from shared.top_site_cache import is_approved_site
from shared.veridex_protocol import SourceEvidence, VericoreStatementResponse
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
    SNIPPET_NOT_CONTEXT_SIMILAR, IS_SEARCH_WEB_PAGE, FAKE_SNIPPET
)
from validator.statement_context_evaluator import assess_statement_async
from validator.web_page_validator import is_search_web_page

MIN_SNIPPET_CONTEXT_SIMILARITY_SCORE = .65

class SnippetValidator:

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

    async def _fetch_page_text(self, request_id:str, miner_uid: int, url: str) -> str:
        try:
            page_html = await fetch_entire_page(request_id, miner_uid, url)

            if page_html is None:
                return ""

            return page_html

        except Exception as e:
            bt.logging.error(f"{request_id} | {miner_uid} | Error fetching page text in rendered page: {e}")
            return ""


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
                else:
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
            # bt.logging.info(f"{request_id} | {miner_uid} | {miner_evidence.url} | {unquote(values[0])} | {miner_evidence.excerpt} | Checking query parameters")
            #
            # is_similar_excerpt, statement_similarity_score,  = await self.is_snippet_similar_to_statement(
            #     request_id, miner_uid, miner_evidence.url, miner_evidence.excerpt, unquote(values[0]), similarity_query_parameter_threshold
            # )
            #
            # bt.logging.info(f"{request_id} | {miner_uid} | {miner_evidence.url} | {values[0]} | {miner_evidence.excerpt} | Is similar to query parameter: {is_similar_excerpt}, {statement_similarity_score}")
            #
            # # Using search as evidence - 5
            # if is_similar_excerpt:

            if True:
                bt.logging.info(f"{request_id} | {miner_uid} | {miner_evidence.url} | {values[0]} | Query Parameter Excerpt is the SAME")
                snippet_score = USING_SEARCH_AS_EVIDENCE
                vericore_miner_response = VericoreStatementResponse(
                    url=miner_evidence.url,
                    excerpt=miner_evidence.excerpt,
                    domain=domain,
                    snippet_found=False,
                    local_score=0.0,
                    snippet_score=snippet_score,
                    snippet_score_reason="using_search_as_evidence",
                )
                return vericore_miner_response

        parsed = urlparse(miner_evidence.url)
        path_parts = [unquote_plus(part.strip()) for part in parsed.path.split('/') if part]

        for part_index, part in enumerate(path_parts):
            if part.lower() == "search":
            # if re.search(r"[\\/]*search[\\/]*", part):
                bt.logging.info(f"{request_id} | {miner_uid} | {miner_evidence.url} | {part} | search is part of url")
                snippet_score = USING_SEARCH_AS_EVIDENCE
                return VericoreStatementResponse(
                    url=miner_evidence.url,
                    excerpt=miner_evidence.excerpt,
                    domain=domain,
                    snippet_found=False,
                    local_score=0.0,
                    snippet_score=snippet_score,
                    snippet_score_reason="using_search_as_evidence",
                )

            if part_index == len(path_parts) - 1:
                word_count = len(part.split())
                # has_punctuation = bool(re.search(r"[.,:;!?]", decoded_part))

                if word_count > 3:
                    bt.logging.info(f"{request_id} | {miner_uid} | {miner_evidence.url} | {part} | Last url search parameter is sentence")
                    snippet_score = USING_SEARCH_AS_EVIDENCE
                    return VericoreStatementResponse(
                        url=miner_evidence.url,
                        excerpt=miner_evidence.excerpt,
                        domain=domain,
                        snippet_found=False,
                        local_score=0.0,
                        snippet_score=snippet_score,
                        snippet_score_reason="using_search_as_evidence",
                    )

                if "%20" in part:
                    bt.logging.info(f"{request_id} | {miner_uid} | {miner_evidence.url} | {part} | Last url search parameter is sentence:%20 ")
                    snippet_score = USING_SEARCH_AS_EVIDENCE
                    return VericoreStatementResponse(
                        url=miner_evidence.url,
                        excerpt=miner_evidence.excerpt,
                        domain=domain,
                        snippet_found=False,
                        local_score=0.0,
                        snippet_score=snippet_score,
                        snippet_score_reason="using_search_as_evidence:%20"
                    )

                is_similar_excerpt, statement_similarity_score,  = await self.is_snippet_similar_to_statement(
                    request_id, miner_uid, miner_evidence.url, miner_evidence.excerpt, part
                )
                if is_similar_excerpt:
                    bt.logging.info(f"{request_id} | {miner_uid} | {miner_evidence.url} | {part} | Excerpt is same as url")
                    snippet_score = USING_SEARCH_AS_EVIDENCE
                    return VericoreStatementResponse(
                        url=miner_evidence.url,
                        excerpt=miner_evidence.excerpt,
                        domain=domain,
                        snippet_found=False,
                        local_score=0.0,
                        snippet_score=snippet_score,
                        snippet_score_reason="using_search_as_evidence",
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
            snippet_score = BLACKLISTED_URL_SCORE
            return VericoreStatementResponse(
                url=miner_evidence.url,
                excerpt=miner_evidence.excerpt,
                domain=domain,
                snippet_found=False,
                local_score=0.0,
                snippet_score=snippet_score,
                snippet_score_reason="blacklisted_url"
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
            snippet_score = DOMAIN_REGISTERED_RECENTLY
            return VericoreStatementResponse(
                url=miner_evidence.url,
                excerpt=miner_evidence.excerpt,
                domain=domain,
                snippet_found=False,
                local_score=0.0,
                snippet_score=snippet_score,
                snippet_score_reason="domain_is_recently_registered"
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

    async def validate_miner_snippet(
        self,
        request_id: str,
        miner_uid: int,
        original_statement: str,
        miner_evidence: SourceEvidence
    ) -> VericoreStatementResponse:
        start_time = time.perf_counter()

        bt.logging.info(
            f"{request_id} | {miner_uid} | {miner_evidence.url} | Verifying miner snippet"
        )
        try:
            try:
                domain = self._extract_domain(miner_evidence.url)
            except InsecureProtocolError:
                bt.logging.error(f"{request_id} | {miner_uid} | {miner_evidence.url} | Url provided isn't SSL")
                snippet_score = SSL_DOMAIN_REQUIRED
                vericore_miner_response = VericoreStatementResponse(
                    url=miner_evidence.url,
                    excerpt=miner_evidence.excerpt,
                    snippet_found=False,
                    local_score=0.0,
                    snippet_score=snippet_score,
                    snippet_score_reason="ssl_url_required"
                )
                return vericore_miner_response

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

            snippet_str = miner_evidence.excerpt.strip()
            # snippet was not processed - Score: -1
            if not snippet_str:
                snippet_score = NO_SNIPPET_PROVIDED
                vericore_miner_response = VericoreStatementResponse(
                    url=miner_evidence.url,
                    excerpt=miner_evidence.excerpt,
                    domain=domain,
                    snippet_found=False,
                    local_score=0.0,
                    snippet_score=snippet_score,
                    snippet_score_reason="no_snippet_provided"
                )
                return vericore_miner_response

            # if article is the same as the excerpt - Score: -5
            if snippet_str == original_statement.strip():
                snippet_score = SNIPPET_SAME_AS_STATEMENT
                vericore_miner_response = VericoreStatementResponse(
                    url=miner_evidence.url,
                    excerpt=miner_evidence.excerpt,
                    domain=domain,
                    snippet_found=False,
                    local_score=0.0,
                    snippet_score=snippet_score,
                    snippet_score_reason="snippet_same_as_statement"
                )
                return vericore_miner_response

            # Invalid excerpt - Score: -5
            if not self.is_valid_separator_sentence(snippet_str):
                snippet_score = INVALID_SNIPPET_EXCERPT
                return VericoreStatementResponse(
                    url=miner_evidence.url,
                    excerpt=miner_evidence.excerpt,
                    domain=domain,
                    snippet_found=False,
                    local_score=0.0,
                    snippet_score=snippet_score,
                    snippet_score_reason="invalid_excerpt"
                )

            bt.logging.info(f"{request_id} | {miner_uid} | {miner_evidence.url} | Is snippet in same context as statement")

            is_similar_excerpt, statement_similarity_score,  = await self.is_snippet_similar_to_statement(
                request_id, miner_uid, miner_evidence.url, original_statement, snippet_str
            )

            bt.logging.info(f"{request_id} | {miner_uid} | {miner_evidence.url} | Is the same statement: {is_similar_excerpt} | Snippet Context: {statement_similarity_score}")

            if is_similar_excerpt:
                snippet_score = EXCERPT_TOO_SIMILAR
                return VericoreStatementResponse(
                    url=miner_evidence.url,
                    excerpt=miner_evidence.excerpt,
                    domain=domain,
                    snippet_found=False,
                    local_score=0.0,
                    snippet_score=snippet_score,
                    snippet_score_reason="excerpt_too_similar",
                    statement_similarity_score=statement_similarity_score
                )

            bt.logging.info(
                f"{request_id} | {miner_uid} | {miner_evidence.url} | Fetching page text"
            )

            # Fetch page text
            page_text = await self._fetch_page_text(request_id, miner_uid, miner_evidence.url)

            # Could not extract page text from url
            if page_text == '':
                snippet_score = COULD_NOT_GET_PAGE_TEXT_FROM_URL
                vericore_miner_response = VericoreStatementResponse(
                    url=miner_evidence.url,
                    excerpt=miner_evidence.excerpt,
                    domain=domain,
                    snippet_found=False,
                    local_score=0.0,
                    snippet_score=snippet_score,
                    snippet_score_reason="could_not_extract_html_from_url"
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
                    snippet_score_reason="is_search_web_page"
                )

            bt.logging.info(
                f"{request_id} | {miner_uid} | {miner_evidence.url} | Verifying snippet in rendered page"
            )

            assessment_result = await assess_statement_async(
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
                        rejection_reason = assessment_result.get("reason")
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
                        rejection_reason = assessment_result.get("reason")
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
                        snippet_score_reason="is_search_web_page",
                        rejection_reason = assessment_result.get("reason")
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
                    page_text=page_text if DEBUG_LOCAL else ""
                )
                return vericore_miner_response

            context_similarity_score = calculate_similarity_score(
                statement=original_statement.strip(),
                excerpt=miner_evidence.excerpt
            )

            bt.logging.info(
                f"{request_id} | {miner_uid} | {miner_evidence.url} | Context similarity: {context_similarity_score} "
            )

            # Zero score if excerpt isn't context similar to statement
            if context_similarity_score < MIN_SNIPPET_CONTEXT_SIMILARITY_SCORE:
                snippet_score = SNIPPET_NOT_CONTEXT_SIMILAR
                return VericoreStatementResponse(
                    url=miner_evidence.url,
                    excerpt=miner_evidence.excerpt,
                    domain=domain,
                    snippet_found=False,
                    local_score=0.0,
                    snippet_score=snippet_score,
                    snippet_score_reason="snippet_not_context_similar",
                    context_similarity_score=context_similarity_score,
                    page_text=""
                )

            # Determine whether statement is neutral/corroborated or refuted
            probs, local_score = await score_statement_distribution(
                statement=original_statement.strip(),
                snippet=miner_evidence.excerpt
            )

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
                statement_similarity_score=statement_similarity_score,
                is_similar_context=is_similar_excerpt
            )
            end_time = time.time()
            bt.logging.info(
                f"{request_id} | {miner_uid} | {miner_evidence.url} | Finished verifying miner snippet at {end_time} (Duration: {end_time - start_time})"
            )
            return vericore_miner_response
        except Exception as e:
            bt.logging.error(
                f"{request_id} | {miner_uid} | Error fetching miner snippet {e}"
            )
            snippet_score = -1.0
            vericore_miner_response = VericoreStatementResponse(
                url=miner_evidence.url,
                excerpt=miner_evidence.excerpt,
                domain=domain,
                snippet_found=False,
                local_score=0.0,
                snippet_score=snippet_score,
                snippet_score_reason="error_verifying_miner_snippet"
            )
            return vericore_miner_response



validator = SnippetValidator()

async def run_validate_miner_snippet(
    request_id: str,
    miner_uid: int,
    original_statement: str,
    miner_evidence: SourceEvidence
) -> VericoreStatementResponse:
    return await validator.validate_miner_snippet(
        request_id,
        miner_uid,
        original_statement,
        miner_evidence
    )
