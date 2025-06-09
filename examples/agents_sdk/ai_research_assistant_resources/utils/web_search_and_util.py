# web_search_and_util.py

from bs4 import BeautifulSoup
import requests
from dotenv import load_dotenv
import os

load_dotenv('.env')

api_key = os.getenv('API_KEY')
cse_id = os.getenv('CSE_ID')

TRUNCATE_SCRAPED_TEXT = 50000  # Adjust based on your model's context window
SEARCH_DEPTH = 2  # Default depth for Google Custom Search queries

# ------------------------------------------------------------------
# Optional: patch asyncio to allow nested event loops (e.g., inside Jupyter)
# ------------------------------------------------------------------

try:
    import nest_asyncio  # type: ignore

    # ``nest_asyncio`` monkey-patches the running event-loop so that further
    # calls to ``asyncio.run`` or ``loop.run_until_complete`` do **not** raise
    # ``RuntimeError: This event loop is already running``.  This makes the
    # synchronous helper functions below safe to call in notebook cells while
    # still working unchanged in regular Python scripts.

    nest_asyncio.apply()
except ImportError:  # pragma: no cover
    # ``nest_asyncio`` is an optional dependency.  If it is unavailable we
    # simply skip patching – the helper functions will still work in regular
    # Python scripts but may raise ``RuntimeError`` when called from within
    # environments that already run an event-loop (e.g., Jupyter).
    pass

def search(search_item, api_key, cse_id, search_depth=SEARCH_DEPTH, site_filter=None):
    service_url = 'https://www.googleapis.com/customsearch/v1'

    params = {
        'q': search_item,
        'key': api_key,
        'cx': cse_id,
        'num': search_depth
    }
    
    if api_key is None or cse_id is None:
        raise ValueError("API key and CSE ID are required")

    try:
        response = requests.get(service_url, params=params)
        response.raise_for_status()
        results = response.json()

        # ------------------------------------------------------------------
        # Robust handling – always return a *list* (never ``None``)
        # ------------------------------------------------------------------
        items = results.get("items", [])

        # Optional site filtering
        if site_filter:
            items = [itm for itm in items if site_filter in itm.get("link", "")]
            if not items:
                print(f"No results with {site_filter} found.")

        # Graceful handling of empty results
        if not items:
            print("No search results found.")
            return []

        return items

    except requests.exceptions.RequestException as e:
        print(f"An error occurred during the search: {e}")
        return []




def retrieve_content(url, max_tokens=TRUNCATE_SCRAPED_TEXT):
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')
            for script_or_style in soup(['script', 'style']):
                script_or_style.decompose()

            text = soup.get_text(separator=' ', strip=True)
            characters = max_tokens * 4  # Approximate conversion
            text = text[:characters]
            return text
        except requests.exceptions.RequestException as e:
            print(f"Failed to retrieve {url}: {e}")
            return None
        


async def get_search_results(search_items, search_term: str, character_limit: int = 500):
    # Generate a summary of search results for the given search term
    results_list = []
    for idx, item in enumerate(search_items, start=1):
        url = item.get('link')
        
        snippet = item.get('snippet', '')
        web_content = retrieve_content(url, TRUNCATE_SCRAPED_TEXT)
        
        if web_content is None:
            print(f"Error: skipped URL: {url}")
        else:
            summary = summarize_content(web_content, search_term, character_limit)
            result_dict = {
                'order': idx,
                'link': url,
                'title': snippet,
                'Summary': summary
            }
            results_list.append(result_dict)
    return results_list

# ------------------------------------------------------------------
# Helper using WebPageSummaryAgent for content summarisation
# ------------------------------------------------------------------
# NOTE:
# ``WebPageSummaryAgent`` is an agent wrapper that internally spins up an
# ``agents.Agent`` instance with the correct system prompt for Web page
# summarisation.  Because the ``task`` method on the wrapper is *async*, we
# provide a small synchronous wrapper that takes care of running the coroutine
# irrespective of whether the caller is inside an active event-loop (e.g.
# Jupyter notebooks) or not.

from ai_research_assistant_resources.agents_tools_registry.web_page_summary_agent import WebPageSummaryAgent
import asyncio


def summarize_content(content: str, search_term: str, character_limit: int = 2000) -> str:  # noqa: D401

    # Instantiate the agent with the dynamic instructions.
    agent = WebPageSummaryAgent(search_term=search_term, character_limit=character_limit)

    # Run the agent task, making sure we properly handle the presence (or
    # absence) of an already-running event-loop.
    try:
        return asyncio.run(agent.task(content))
    except RuntimeError:
        # We are *probably* inside an existing event-loop (common in notebooks
        # or async frameworks).  In that case fall back to using the current
        # loop instead of creating a new one.
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(agent.task(content))


# ------------------------------------------------------------------
# High-level convenience API
# ------------------------------------------------------------------


def get_results_for_search_term(
    search_term: str,
    *,
    character_limit: int = 2000,
    search_depth: int = SEARCH_DEPTH,
    site_filter: str | None = None,
) -> list[dict]:
    """Search the Web for *search_term* and return enriched result dictionaries.

    The function handles the entire workflow:

    1. Perform a Google Custom Search using the provided credentials.
    2. Retrieve and clean the contents of each result page.
    3. Generate a concise summary of each page focused on *search_term* using
       :pyfunc:`summarize_content`.

    The returned value is a ``list`` of ``dict`` objects with the following
    keys: ``order``, ``link``, ``title`` and ``Summary``.
    """

    # Step 1 – search.
    search_items = search(
        search_term,
        api_key=api_key,
        cse_id=cse_id,
        search_depth=search_depth,
        site_filter=site_filter,
    )

    # Step 2 & 3 – scrape pages and summarise.
    # ``get_search_results`` is an *async* coroutine.  Execute it and
    # return its result, transparently handling the presence (or absence)
    # of an already-running event loop (e.g. in notebooks).

    try:
        # Prefer ``asyncio.run`` which creates and manages a fresh event
        # loop.  This is the most robust option for regular Python
        # scripts.
        import asyncio  # local import to avoid polluting module top-level

        return asyncio.run(
            get_search_results(search_items, search_term, character_limit)
        )
    except RuntimeError:
        # We probably find ourselves inside an existing event loop (for
        # instance when this helper is invoked from within a Jupyter
        # notebook).  Fall back to re-using the current loop.
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(
            get_search_results(search_items, search_term, character_limit)
        )