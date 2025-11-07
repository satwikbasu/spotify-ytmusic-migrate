"""YouTube Music search module for finding tracks.

This module implements YouTube Music search functionality with rate limiting,
error handling, and ISRC-based exact matching for high-accuracy results.
"""

import time
import logging
from typing import List, Optional, Dict, Any

from ytmusicapi import YTMusic
from ytmusicapi.exceptions import YTMusicServerError

from src.utils.rate_limiter import RateLimiter
from src.utils.string_utils import sanitize_for_search


# Configure logging
logger = logging.getLogger(__name__)


class YouTubeSearcher:
    """Searches YouTube Music for tracks with rate limiting and error handling.
    
    Implements conservative search strategies to avoid rate limits while
    maximizing accuracy through ISRC matching and fuzzy text search.
    
    Attributes:
        ytmusic_client: Authenticated YTMusic API client
        rate_limiter: Rate limiter instance for request throttling
    """
    
    # Search configuration
    DEFAULT_LIMIT = 5  # Return top 5 results for fuzzy matching
    ISRC_LIMIT = 1     # ISRC searches only need 1 result (exact match)
    
    # Retry configuration
    MAX_RETRIES = 3
    RETRY_DELAYS = [1.0, 2.0, 4.0]  # Exponential backoff
    
    # Conservative delay between searches (1 second)
    SEARCH_DELAY = 1.0
    
    def __init__(self, ytmusic_client: YTMusic, rate_limiter: RateLimiter):
        """Initialize the YouTube Music searcher.
        
        Args:
            ytmusic_client: Authenticated YTMusic client instance
            rate_limiter: Rate limiter for request throttling
        
        Raises:
            ValueError: If ytmusic_client or rate_limiter is None
        """
        if ytmusic_client is None:
            raise ValueError("ytmusic_client cannot be None")
        if rate_limiter is None:
            raise ValueError("rate_limiter cannot be None")
        
        self.ytmusic_client = ytmusic_client
        self.rate_limiter = rate_limiter
        
        logger.info("YouTubeSearcher initialized")
    
    def search_track(
        self,
        track_name: str,
        artists: List[str]
    ) -> List[Dict[str, Any]]:
        """Search YouTube Music for a track using fuzzy text matching.
        
        Builds a search query from track name and artists, performs rate-limited
        search, and returns top results for fuzzy matching.
        
        Algorithm:
        1. Sanitize track name and artists into search query
        2. Check rate limiter before searching
        3. Perform YouTube Music search (filter='songs', limit=5)
        4. Record request with rate limiter
        5. Apply conservative 1-second delay
        6. Handle 429 rate limit errors with retry
        7. Handle network errors with exponential backoff
        
        Args:
            track_name: Name of the track to search for
            artists: List of artist names (primary artist should be first)
        
        Returns:
            List of YouTube Music track dicts, each containing:
            - videoId: YouTube video ID (str)
            - title: Track title (str)
            - artists: List of artist dicts with 'name' key (List[dict])
            - album: Album dict with 'name' key or None (dict or None)
            - duration: Duration string like "3:45" (str, optional)
            - duration_seconds: Duration in seconds (int, optional)
            
            Returns empty list if no results found or error occurs.
        
        Example:
            >>> searcher = YouTubeSearcher(ytmusic_client, rate_limiter)
            >>> results = searcher.search_track("Blinding Lights", ["The Weeknd"])
            >>> len(results) <= 5
            True
            >>> results[0]['videoId']
            'abc123...'
        """
        if not track_name:
            logger.warning("Empty track name provided to search_track()")
            return []
        
        # Build search query using string utilities
        query = sanitize_for_search(track_name, artists)
        
        if not query:
            logger.warning(f"sanitize_for_search returned empty query for: {track_name}")
            return []
        
        logger.info(f"Searching YouTube Music: '{query}'")
        
        # Perform search with rate limiting and error handling
        return self._search_with_retry(
            query=query,
            filter_type='songs',
            limit=self.DEFAULT_LIMIT,
            search_type='track'
        )
    
    def search_by_isrc(self, isrc: str) -> Optional[Dict[str, Any]]:
        """Search YouTube Music by ISRC for exact matching.
        
        ISRC (International Standard Recording Code) provides near 100% accuracy
        for track matching. This method should be tried before fuzzy matching.
        
        Args:
            isrc: ISRC code (e.g., "USRC17607839")
        
        Returns:
            YouTube Music track dict if found (see search_track for format),
            or None if not found or error occurs.
        
        Example:
            >>> searcher = YouTubeSearcher(ytmusic_client, rate_limiter)
            >>> result = searcher.search_by_isrc("USRC17607839")
            >>> result['videoId'] if result else None
            'xyz789...'
        """
        if not isrc:
            logger.warning("Empty ISRC provided to search_by_isrc()")
            return None
        
        # ISRC search query format
        query = f"isrc:{isrc}"
        
        logger.info(f"Searching YouTube Music by ISRC: {isrc}")
        
        # Perform search with rate limiting
        results = self._search_with_retry(
            query=query,
            filter_type='songs',
            limit=self.ISRC_LIMIT,
            search_type='isrc'
        )
        
        # Return first result or None
        if results:
            logger.info(f"ISRC match found for {isrc}: {results[0].get('title', 'Unknown')}")
            return results[0]
        
        logger.info(f"No ISRC match found for {isrc}")
        return None
    
    def _search_with_retry(
        self,
        query: str,
        filter_type: str,
        limit: int,
        search_type: str
    ) -> List[Dict[str, Any]]:
        """Perform YouTube Music search with retry logic and rate limiting.
        
        Internal method that handles:
        - Rate limit checking before request
        - Request execution
        - Rate limit recording after request
        - Conservative delay
        - 429 error handling with retry
        - Network error handling with exponential backoff
        
        Args:
            query: Search query string
            filter_type: YouTube Music filter ('songs', 'videos', etc.)
            limit: Maximum number of results to return
            search_type: Type of search for logging ('track', 'isrc')
        
        Returns:
            List of search results or empty list on error.
        """
        for attempt in range(self.MAX_RETRIES):
            try:
                # Check rate limiter before making request
                if not self.rate_limiter.check_limit():
                    logger.warning(
                        f"Rate limit exceeded, waiting before {search_type} search: {query}"
                    )
                    # Rate limiter will handle the wait internally
                    # Try again after the wait
                    if not self.rate_limiter.check_limit():
                        logger.error(f"Rate limit still exceeded after wait for: {query}")
                        return []
                
                # Perform the search
                logger.debug(f"Executing YouTube Music search (attempt {attempt + 1}): {query}")
                results = self.ytmusic_client.search(
                    query=query,
                    filter=filter_type,
                    limit=limit
                )
                
                # Record successful request with rate limiter
                self.rate_limiter.record_request()
                
                # Apply conservative delay between searches
                time.sleep(self.SEARCH_DELAY)
                
                # Process and validate results
                if not results:
                    logger.info(f"No results found for {search_type} search: {query}")
                    return []
                
                # Validate and normalize results
                validated_results = self._validate_results(results, query)
                
                logger.info(
                    f"Found {len(validated_results)} results for {search_type} search: {query}"
                )
                return validated_results
            
            except YTMusicServerError as e:
                # Handle 429 rate limit errors
                if '429' in str(e) or 'rate limit' in str(e).lower():
                    logger.warning(f"429 rate limit error on attempt {attempt + 1}: {e}")
                    
                    # Let rate limiter handle the backoff
                    self.rate_limiter.handle_429()
                    
                    # Retry once after 429
                    if attempt < self.MAX_RETRIES - 1:
                        logger.info(f"Retrying {search_type} search after 429 error...")
                        continue
                    else:
                        logger.error(f"Max retries exceeded for 429 error: {query}")
                        return []
                
                # Other server errors
                logger.error(f"YouTube Music server error on attempt {attempt + 1}: {e}")
                if attempt < self.MAX_RETRIES - 1:
                    delay = self.RETRY_DELAYS[attempt]
                    logger.info(f"Retrying in {delay}s...")
                    time.sleep(delay)
                    continue
                else:
                    logger.error(f"Max retries exceeded for server error: {query}")
                    return []
            
            except ConnectionError as e:
                # Network connectivity issues
                logger.error(f"Connection error on attempt {attempt + 1}: {e}")
                if attempt < self.MAX_RETRIES - 1:
                    delay = self.RETRY_DELAYS[attempt]
                    logger.info(f"Retrying in {delay}s due to connection error...")
                    time.sleep(delay)
                    continue
                else:
                    logger.error(f"Max retries exceeded for connection error: {query}")
                    return []
            
            except Exception as e:
                # Unexpected errors
                logger.error(
                    f"Unexpected error during {search_type} search (attempt {attempt + 1}): {e}",
                    exc_info=True
                )
                if attempt < self.MAX_RETRIES - 1:
                    delay = self.RETRY_DELAYS[attempt]
                    logger.info(f"Retrying in {delay}s due to unexpected error...")
                    time.sleep(delay)
                    continue
                else:
                    logger.error(f"Max retries exceeded for unexpected error: {query}")
                    return []
        
        # Should not reach here, but return empty list as fallback
        logger.error(f"Search failed after all retries: {query}")
        return []
    
    def _validate_results(
        self,
        results: List[Dict[str, Any]],
        query: str
    ) -> List[Dict[str, Any]]:
        """Validate and normalize search results.
        
        Ensures each result has required fields and converts duration strings
        to seconds for easier comparison.
        
        Args:
            results: Raw search results from YTMusic
            query: Original search query (for logging)
        
        Returns:
            List of validated and normalized results.
        """
        validated = []
        
        for idx, result in enumerate(results):
            try:
                # Check required fields
                if not isinstance(result, dict):
                    logger.warning(f"Result {idx} is not a dict, skipping: {type(result)}")
                    continue
                
                if 'videoId' not in result:
                    logger.warning(f"Result {idx} missing 'videoId', skipping")
                    continue
                
                if 'title' not in result:
                    logger.warning(f"Result {idx} missing 'title', skipping")
                    continue
                
                # Parse duration if available (format: "3:45")
                if 'duration' in result and result['duration']:
                    duration_seconds = self._parse_duration(result['duration'])
                    if duration_seconds:
                        result['duration_seconds'] = duration_seconds
                
                # Ensure artists is a list
                if 'artists' not in result or not isinstance(result['artists'], list):
                    result['artists'] = []
                
                validated.append(result)
            
            except Exception as e:
                logger.error(
                    f"Error validating result {idx} for query '{query}': {e}",
                    exc_info=True
                )
                continue
        
        return validated
    
    def _parse_duration(self, duration_str: str) -> Optional[int]:
        """Parse YouTube Music duration string to seconds.
        
        Args:
            duration_str: Duration string like "3:45" or "1:23:45"
        
        Returns:
            Duration in seconds or None if parsing fails.
        
        Example:
            >>> searcher._parse_duration("3:45")
            225
            >>> searcher._parse_duration("1:23:45")
            5025
        """
        try:
            parts = duration_str.split(':')
            
            if len(parts) == 2:
                # Format: "MM:SS"
                minutes, seconds = map(int, parts)
                return minutes * 60 + seconds
            
            elif len(parts) == 3:
                # Format: "HH:MM:SS"
                hours, minutes, seconds = map(int, parts)
                return hours * 3600 + minutes * 60 + seconds
            
            else:
                logger.warning(f"Unexpected duration format: {duration_str}")
                return None
        
        except (ValueError, AttributeError) as e:
            logger.warning(f"Failed to parse duration '{duration_str}': {e}")
            return None
