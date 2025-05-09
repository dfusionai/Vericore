import time
import bittensor as bt
import tldextract
import ipaddress
import re
import os
from urllib.parse import urlparse

from shared.exceptions import InsecureProtocolError
from shared.top_level_domain_cache import is_approved_domain
from shared.veridex_protocol import SourceEvidence, VericoreStatementResponse
from validator.domain_validator import domain_is_recently_registered
from validator.quality_model import score_statement_distribution
from validator.snippet_fetcher import fetch_entire_page
from validator.verify_context_quality_model import verify_text_similarity

from shared.debug_util import DEBUG_LOCAL

from shared.scores import (
    NO_SNIPPET_PROVIDED,
    SNIPPET_SAME_AS_STATEMENT,
    COULD_NOT_GET_PAGE_TEXT_FROM_URL,
    SNIPPET_NOT_VERIFIED_IN_URL,
    DOMAIN_REGISTERED_RECENTLY,
    SSL_DOMAIN_REQUIRED,
    APPROVED_URL_MULTIPLIER, EXCERPT_TOO_SIMILAR
)

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
        self, request_id: str, miner_uid: int, url: str, statement: str, snippet_text: str
    ) :
        try:
            bt.logging.info(f"{request_id} | {miner_uid} | url: {url} | Checking whether the snippet provided is the same as the statement")
            return await verify_text_similarity(statement, snippet_text)

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

            # check if snippet comes from verified domain
            approved_url_multiplier = 1
            if is_approved_domain(request_id, miner_uid, domain):
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

            bt.logging.info(f"{request_id} | {miner_uid} | {miner_evidence.url} | Is snippet in same context as statement")

            is_similar_excerpt, statement_similarity_score,  = await self.is_snippet_similar_to_statement(
                request_id, miner_uid, miner_evidence.url, original_statement, snippet_str
            )

            bt.logging.info(f"{request_id} | {miner_uid} | {miner_evidence.url} | Is the same statement: {is_similar_excerpt} | Snippet Context: {statement_similarity_score}")

            if is_similar_excerpt:
                snippet_score = EXCERPT_TOO_SIMILAR
                vericore_miner_response = VericoreStatementResponse(
                    url=miner_evidence.url,
                    excerpt=miner_evidence.excerpt,
                    domain=domain,
                    snippet_found=False,
                    local_score=0.0,
                    snippet_score=snippet_score,
                    snippet_score_reason="excerpt_too_similar",
                    statement_similarity_score=statement_similarity_score
                )
                return vericore_miner_response


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

            bt.logging.info(
                f"{request_id} | {miner_uid} | {miner_evidence.url} | Verifying snippet in rendered page"
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

            # Dont score if domain was registered within 30 days.
            domain_registered_recently = await domain_is_recently_registered(domain)

            bt.logging.info(
                f"{request_id} | {miner_uid} | {miner_evidence.url} | Is domain registered recently: {domain_registered_recently}"
            )
            if domain_registered_recently:
                snippet_score = DOMAIN_REGISTERED_RECENTLY
                vericore_miner_response = VericoreStatementResponse(
                    url=miner_evidence.url,
                    excerpt=miner_evidence.excerpt,
                    domain=domain,
                    snippet_found=False,
                    local_score=0.0,
                    snippet_score=snippet_score,
                    snippet_score_reason="domain_is_recently_registered"
                )
                return vericore_miner_response

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
