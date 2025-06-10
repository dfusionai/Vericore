from validator.context_similarity_validator import calculate_similarity_score

search_page_text = [
    "You searched for",
    "Search results for",
    "Nothing matched your search terms",
    "We couldn’t find any results",
    "Showing results for your query"
]

def is_search_web_page(web_page: str) -> bool:
    for search_page in search_page_text:
        context_similarity_score = calculate_similarity_score(web_page, search_page)
        if context_similarity_score > 0.7:
            return True

    return False


