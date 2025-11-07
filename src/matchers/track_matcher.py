"""Track matching module for Spotify to YouTube Music migration.

This module implements fuzzy matching algorithms to find the best YouTube Music
track match for a given Spotify track, using weighted similarity scores for
title, artist, album, and duration validation.
"""

from typing import List, Optional, Tuple, Dict, Any
from rapidfuzz import fuzz

from src.utils.string_utils import (
    normalize_string,
    sanitize_for_search,
    extract_featured_artists
)


class TrackMatcher:
    """Matches Spotify tracks to YouTube Music tracks using fuzzy matching.
    
    Implements a weighted scoring algorithm that considers:
    - Title similarity (60% weight)
    - Artist similarity (30% weight)
    - Album similarity (5% weight)
    - Duration validation (5% weight + bonus multiplier)
    
    Attributes:
        threshold: Minimum confidence score (0-100) required for a match.
                  Recommended range: 60-85 (higher = stricter matching)
    """
    
    # Scoring weights
    TITLE_WEIGHT = 0.60
    ARTIST_WEIGHT = 0.30
    ALBUM_WEIGHT = 0.05
    DURATION_WEIGHT = 0.05
    
    # Duration thresholds (in seconds)
    DURATION_EXCELLENT = 2    # <= 2s diff: 1.3x multiplier
    DURATION_GOOD = 5         # <= 5s diff: 1.15x multiplier
    DURATION_ACCEPTABLE = 10  # <= 10s diff: 1.05x multiplier
    DURATION_REJECT = 30      # > 30s diff: auto-reject
    
    def __init__(self, threshold: int = 75):
        """Initialize the track matcher.
        
        Args:
            threshold: Minimum confidence score (0-100) for a valid match.
                      Default 75 provides balanced precision/recall.
                      - 60-70: More matches, lower precision
                      - 75-80: Balanced (recommended)
                      - 85-95: Fewer matches, higher precision
        
        Raises:
            ValueError: If threshold is not between 0 and 100.
        """
        if not 0 <= threshold <= 100:
            raise ValueError(f"Threshold must be between 0 and 100, got {threshold}")
        
        self.threshold = threshold
    
    def calculate_similarity(
        self,
        spotify_track: Dict[str, Any],
        youtube_track: Dict[str, Any]
    ) -> float:
        """Calculate similarity score between Spotify and YouTube tracks.
        
        Implements weighted scoring algorithm:
        1. Normalize track data from both sources
        2. Calculate title similarity (60% weight) using token_sort_ratio
        3. Calculate artist similarity (30% weight) using ratio
        4. Calculate album similarity (5% weight) if available
        5. Calculate duration bonus (5% weight) and multiplier
        6. Combine scores with duration multiplier
        7. Cap final score at 100
        
        Args:
            spotify_track: Spotify track dict with keys:
                - name: Track name (str)
                - artists: List of artist names (List[str])
                - album: Album name (str)
                - duration_ms: Duration in milliseconds (int)
            youtube_track: YouTube Music track dict with keys:
                - videoId: YouTube video ID (str)
                - title: Video title (str)
                - artists: List of artist dicts with 'name' key (List[dict])
                - album: Optional dict with 'name' key (dict or None)
                - duration_seconds: Optional duration in seconds (int or None)
        
        Returns:
            Similarity score from 0.0 to 100.0. Returns 0.0 if duration
            difference exceeds DURATION_REJECT threshold.
        
        Example:
            >>> matcher = TrackMatcher(threshold=75)
            >>> spotify = {
            ...     'name': 'Blinding Lights',
            ...     'artists': ['The Weeknd'],
            ...     'album': 'After Hours',
            ...     'duration_ms': 200040
            ... }
            >>> youtube = {
            ...     'videoId': 'abc123',
            ...     'title': 'The Weeknd - Blinding Lights',
            ...     'artists': [{'name': 'The Weeknd'}],
            ...     'album': {'name': 'After Hours'},
            ...     'duration_seconds': 200
            ... }
            >>> score = matcher.calculate_similarity(spotify, youtube)
            >>> score > 90  # Should be very high match
            True
        """
        # Normalize track data
        norm_spotify = self.normalize_track_data(spotify_track, "spotify")
        norm_youtube = self.normalize_track_data(youtube_track, "youtube")
        
        # 1. Title similarity (60% weight) - token_sort_ratio handles word order
        title_score = fuzz.token_sort_ratio(
            norm_spotify['title'],
            norm_youtube['title']
        )
        
        # 2. Artist similarity (30% weight) - compare primary artist
        # Join all artists for comprehensive comparison
        spotify_artists = ' '.join(norm_spotify['artists'])
        youtube_artists = ' '.join(norm_youtube['artists'])
        artist_score = fuzz.ratio(spotify_artists, youtube_artists)
        
        # 3. Album similarity (5% weight) - only if both have albums
        album_score = 0.0
        if norm_spotify['album'] and norm_youtube['album']:
            album_score = fuzz.ratio(
                norm_spotify['album'],
                norm_youtube['album']
            )
        
        # 4. Duration validation and scoring (5% weight + multiplier)
        duration_multiplier = 1.0
        duration_bonus = 0.0
        
        spotify_duration_sec = norm_spotify['duration_ms'] / 1000
        youtube_duration_sec = norm_youtube.get('duration_seconds', 0)
        
        if youtube_duration_sec > 0:
            duration_diff = abs(spotify_duration_sec - youtube_duration_sec)
            
            # Auto-reject if duration difference too large
            if duration_diff > self.DURATION_REJECT:
                return 0.0
            
            # Calculate duration bonus and multiplier based on accuracy
            if duration_diff <= self.DURATION_EXCELLENT:
                duration_multiplier = 1.3  # 30% bonus for near-perfect match
                duration_bonus = 100.0
            elif duration_diff <= self.DURATION_GOOD:
                duration_multiplier = 1.15  # 15% bonus for good match
                duration_bonus = 80.0
            elif duration_diff <= self.DURATION_ACCEPTABLE:
                duration_multiplier = 1.05  # 5% bonus for acceptable match
                duration_bonus = 60.0
            else:
                # No multiplier, but give partial credit
                duration_bonus = 40.0
        
        # 5. Combine weighted scores
        combined_score = (
            title_score * self.TITLE_WEIGHT +
            artist_score * self.ARTIST_WEIGHT +
            album_score * self.ALBUM_WEIGHT +
            duration_bonus * self.DURATION_WEIGHT
        ) * duration_multiplier
        
        # Cap at 100 and return
        return min(combined_score, 100.0)
    
    def match_track(
        self,
        spotify_track: Dict[str, Any],
        youtube_results: List[Dict[str, Any]]
    ) -> Tuple[Optional[str], float]:
        """Find the best matching YouTube track for a Spotify track.
        
        Iterates through all YouTube search results, calculates similarity
        scores, and returns the best match that exceeds the threshold.
        
        Args:
            spotify_track: Spotify track dict (see calculate_similarity for format)
            youtube_results: List of YouTube Music track dicts from search results
        
        Returns:
            Tuple of (video_id, confidence_score):
            - If match found: (video_id: str, score: float)
            - If no match: (None, 0.0)
        
        Example:
            >>> matcher = TrackMatcher(threshold=75)
            >>> spotify_track = {
            ...     'name': 'Shape of You',
            ...     'artists': ['Ed Sheeran'],
            ...     'album': '÷',
            ...     'duration_ms': 233713
            ... }
            >>> youtube_results = [
            ...     {
            ...         'videoId': 'JGwWNGJdvx8',
            ...         'title': 'Ed Sheeran - Shape of You',
            ...         'artists': [{'name': 'Ed Sheeran'}],
            ...         'duration_seconds': 234
            ...     },
            ...     {
            ...         'videoId': 'xyz456',
            ...         'title': 'Shape of You Cover',
            ...         'artists': [{'name': 'Random Artist'}],
            ...         'duration_seconds': 210
            ...     }
            ... ]
            >>> video_id, score = matcher.match_track(spotify_track, youtube_results)
            >>> video_id
            'JGwWNGJdvx8'
            >>> score > 90
            True
        """
        if not youtube_results:
            return None, 0.0
        
        best_match_id = None
        best_score = 0.0
        
        for youtube_track in youtube_results:
            # Calculate similarity score
            score = self.calculate_similarity(spotify_track, youtube_track)
            
            # Track best match
            if score > best_score:
                best_score = score
                best_match_id = youtube_track.get('videoId')
        
        # Return match only if it exceeds threshold
        if best_score >= self.threshold:
            return best_match_id, best_score
        
        return None, 0.0
    
    def normalize_track_data(
        self,
        track: Dict[str, Any],
        source: str
    ) -> Dict[str, Any]:
        """Normalize track data for consistent comparison.
        
        Applies string normalization (lowercase, accent removal, etc.) to
        track metadata from either Spotify or YouTube Music sources.
        
        Args:
            track: Track dict from Spotify or YouTube Music
            source: Either "spotify" or "youtube" to indicate data format
        
        Returns:
            Normalized track dict with keys:
            - title: Normalized track name (str)
            - artists: List of normalized artist names (List[str])
            - album: Normalized album name or empty string (str)
            - duration_ms: Duration in milliseconds (int)
            - duration_seconds: Duration in seconds (int, YouTube only)
        
        Raises:
            ValueError: If source is not "spotify" or "youtube"
        
        Example:
            >>> matcher = TrackMatcher()
            >>> spotify_track = {
            ...     'name': 'Café Society',
            ...     'artists': ['José González'],
            ...     'album': 'Veneer',
            ...     'duration_ms': 240000
            ... }
            >>> normalized = matcher.normalize_track_data(spotify_track, 'spotify')
            >>> normalized['title']
            'cafe society'
            >>> normalized['artists']
            ['jose gonzalez']
        """
        if source not in ("spotify", "youtube"):
            raise ValueError(f"Source must be 'spotify' or 'youtube', got '{source}'")
        
        normalized = {}
        
        if source == "spotify":
            # Extract and normalize Spotify track data
            track_name = track.get('name', '')
            
            # Extract featured artists from track name
            clean_name, featured = extract_featured_artists(track_name)
            
            # Normalize track title
            normalized['title'] = normalize_string(clean_name)
            
            # Normalize artist names (combine main + featured)
            artists = track.get('artists', [])
            all_artists = list(artists) + featured
            normalized['artists'] = [
                normalize_string(artist) for artist in all_artists if artist
            ]
            
            # Normalize album name
            album = track.get('album', '')
            normalized['album'] = normalize_string(album) if album else ''
            
            # Duration (keep original ms)
            normalized['duration_ms'] = track.get('duration_ms', 0)
        
        else:  # source == "youtube"
            # Extract and normalize YouTube Music track data
            title = track.get('title', '')
            
            # Extract featured artists from title
            clean_title, featured = extract_featured_artists(title)
            
            # Normalize title
            normalized['title'] = normalize_string(clean_title)
            
            # Normalize artist names from YouTube format
            artists_data = track.get('artists', [])
            artist_names = [
                artist.get('name', '') for artist in artists_data
                if isinstance(artist, dict)
            ]
            all_artists = artist_names + featured
            normalized['artists'] = [
                normalize_string(artist) for artist in all_artists if artist
            ]
            
            # Normalize album name (YouTube albums are optional dicts)
            album_data = track.get('album')
            if album_data and isinstance(album_data, dict):
                album_name = album_data.get('name', '')
                normalized['album'] = normalize_string(album_name) if album_name else ''
            else:
                normalized['album'] = ''
            
            # Duration (convert to ms for consistency, keep seconds for calculation)
            duration_sec = track.get('duration_seconds', 0)
            normalized['duration_seconds'] = duration_sec
            normalized['duration_ms'] = duration_sec * 1000
        
        return normalized
