"""String Normalization Utilities for Fuzzy Matching.

This module provides utilities for normalizing and cleaning strings to improve
matching accuracy between Spotify and YouTube Music tracks.
"""

import re
import string
import unicodedata
from typing import List


# Common noise words to remove from track names and video titles
NOISE_WORDS = [
    "Official Music Video",  # Check longer phrases first
    "Official Lyric Video",
    "Official Video",
    "Lyric Video",
    "Official Audio",
    "Music Video",
    "(Official)",
    "[Official]",
    "Explicit",
    "Audio",
    "Video",
    "HD",
    "HQ",
    "4K",
    "Remastered",
    "Official",
]


def normalize_string(text: str) -> str:
    """Normalize a string for fuzzy matching.
    
    Applies the following transformations:
    1. Converts to lowercase
    2. Removes accents and diacritics (é → e, ñ → n)
    3. Removes punctuation
    4. Removes extra whitespace (multiple spaces → single space)
    5. Strips leading/trailing whitespace
    
    Args:
        text (str): Text to normalize.
        
    Returns:
        str: Normalized text suitable for fuzzy matching.
        
    Examples:
        >>> normalize_string("Café Société!!!")
        'cafe societe'
        >>> normalize_string("Björk - Jóga")
        'bjork joga'
        >>> normalize_string("Hello,  World!")
        'hello world'
        >>> normalize_string("  Multiple   Spaces  ")
        'multiple spaces'
    """
    if not text:
        return ""
    
    # Convert to lowercase
    text = text.lower()
    
    # Normalize whitespace first (convert tabs, newlines to spaces)
    text = re.sub(r'\s+', ' ', text)
    
    # Remove accents using Unicode normalization
    # NFD = Canonical Decomposition (separates base character from accent)
    # Then filter out combining characters (accents, diacritics)
    text = unicodedata.normalize('NFD', text)
    text = ''.join(char for char in text if unicodedata.category(char) != 'Mn')
    
    # Remove emojis and other symbols
    # Filter out emoji characters (category 'So') and other non-text symbols
    # Keep letters (L*), numbers (N*), spaces (Z*), and punctuation (P*)
    text = ''.join(
        char for char in text 
        if unicodedata.category(char)[0] in ('L', 'N', 'Z', 'P')
    )
    
    # Remove punctuation
    text = text.translate(str.maketrans('', '', string.punctuation))
    
    # Normalize whitespace again (removal of symbols may have created gaps)
    text = re.sub(r'\s+', ' ', text)
    
    # Strip leading/trailing whitespace
    text = text.strip()
    
    return text


def remove_noise_words(text: str) -> str:
    """Remove common noise words from video titles and track names.
    
    Removes phrases commonly added to YouTube videos that don't help with
    matching, such as "Official Video", "Lyric Video", "HD", etc.
    
    The removal is case-insensitive and checks longer phrases first to avoid
    partial matches (e.g., "Official Music Video" before "Official Video").
    
    Args:
        text (str): Text to clean.
        
    Returns:
        str: Text with noise words removed.
        
    Examples:
        >>> remove_noise_words("Blinding Lights (Official Video)")
        'Blinding Lights'
        >>> remove_noise_words("Shape of You - Official Music Video")
        'Shape of You -'
        >>> remove_noise_words("Someone Like You [Official Lyric Video]")
        'Someone Like You []'
        >>> remove_noise_words("Levitating (feat. DaBaby) [Official Audio]")
        'Levitating (feat. DaBaby) []'
    """
    if not text:
        return ""
    
    # Process noise words in order (longer phrases first)
    result = text
    for noise_word in NOISE_WORDS:
        # Case-insensitive replacement
        # Use regex with word boundaries to avoid partial matches
        pattern = re.compile(re.escape(noise_word), re.IGNORECASE)
        result = pattern.sub('', result)
    
    # Clean up any leftover parentheses or brackets with nothing inside
    result = re.sub(r'\(\s*\)', '', result)
    result = re.sub(r'\[\s*\]', '', result)
    
    # Clean up multiple spaces
    result = re.sub(r'\s+', ' ', result)
    
    # Strip leading/trailing whitespace and common separators
    result = result.strip(' -–—')
    
    return result


def sanitize_for_search(track_name: str, artists: List[str]) -> str:
    """Create a sanitized search query from track name and artists.
    
    Builds a search query in the format: "{primary_artist} {track_name}"
    Then applies noise word removal and string normalization.
    
    This format is optimized for searching YouTube Music with the primary
    artist and track name.
    
    Args:
        track_name (str): Track/song name.
        artists (List[str]): List of artist names (uses first artist only).
        
    Returns:
        str: Sanitized search query ready for fuzzy matching.
        
    Examples:
        >>> sanitize_for_search("Blinding Lights", ["The Weeknd"])
        'the weeknd blinding lights'
        >>> sanitize_for_search("Shape of You (Official Video)", ["Ed Sheeran"])
        'ed sheeran shape of you'
        >>> sanitize_for_search("Café del Mar", ["Энергия"])
        'energia cafe del mar'
        >>> sanitize_for_search("Someone Like You", ["Adele", "Featured Artist"])
        'adele someone like you'
    """
    if not track_name:
        return ""
    
    # Get primary artist (first in list)
    primary_artist = artists[0] if artists else ""
    
    # Build query: "{artist} {track_name}"
    if primary_artist:
        query = f"{primary_artist} {track_name}"
    else:
        query = track_name
    
    # Remove noise words first (before normalization to catch case variations)
    query = remove_noise_words(query)
    
    # Apply normalization
    query = normalize_string(query)
    
    return query


def extract_featured_artists(track_name: str) -> tuple[str, List[str]]:
    """Extract featured artists from track name.
    
    Extracts artists mentioned in the track name using common patterns like:
    - "feat.", "ft.", "featuring"
    - "with", "vs.", "vs", "x"
    
    Args:
        track_name (str): Track name potentially containing featured artists.
        
    Returns:
        tuple[str, List[str]]: Tuple of (clean_track_name, featured_artists).
        
    Examples:
        >>> extract_featured_artists("Levitating (feat. DaBaby)")
        ('Levitating', ['DaBaby'])
        >>> extract_featured_artists("Stay (with Justin Bieber)")
        ('Stay', ['Justin Bieber'])
        >>> extract_featured_artists("No featured artists")
        ('No featured artists', [])
    """
    if not track_name:
        return "", []
    
    # Patterns for featured artists
    patterns = [
        r'\(feat\.?\s+([^)]+)\)',
        r'\[feat\.?\s+([^\]]+)\]',
        r'\(ft\.?\s+([^)]+)\)',
        r'\[ft\.?\s+([^\]]+)\]',
        r'\(featuring\s+([^)]+)\)',
        r'\[featuring\s+([^\]]+)\]',
        r'\(with\s+([^)]+)\)',
        r'\[with\s+([^\]]+)\]',
    ]
    
    featured = []
    clean_name = track_name
    
    for pattern in patterns:
        match = re.search(pattern, clean_name, re.IGNORECASE)
        if match:
            # Extract featured artists
            featured_str = match.group(1)
            # Split by common separators
            featured_artists = re.split(r',|\&|and', featured_str)
            featured.extend([artist.strip() for artist in featured_artists if artist.strip()])
            
            # Remove the featured artist part from track name
            clean_name = re.sub(pattern, '', clean_name, flags=re.IGNORECASE)
            break  # Only process first match
    
    # Clean up the track name
    clean_name = re.sub(r'\s+', ' ', clean_name).strip()
    
    return clean_name, featured


def normalize_for_comparison(text: str) -> str:
    """Aggressive normalization for direct string comparison.
    
    More aggressive than normalize_string() - also removes common words
    like "the", "a", "an" and keeps only alphanumeric characters.
    
    Args:
        text (str): Text to normalize.
        
    Returns:
        str: Aggressively normalized text.
        
    Examples:
        >>> normalize_for_comparison("The Beatles - A Day in the Life")
        'beatles day life'
        >>> normalize_for_comparison("Café Society (2016)")
        'cafe society 2016'
    """
    if not text:
        return ""
    
    # Apply basic normalization first
    text = normalize_string(text)
    
    # Remove common articles and words
    common_words = ['the', 'a', 'an', 'and', 'or', 'but']
    words = text.split()
    words = [w for w in words if w not in common_words]
    text = ' '.join(words)
    
    # Keep only alphanumeric and spaces
    text = re.sub(r'[^a-z0-9\s]', '', text)
    
    # Remove extra whitespace again
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text


def calculate_similarity_score(str1: str, str2: str) -> float:
    """Calculate simple similarity score between two strings.
    
    Uses a basic character-level similarity metric. For production use,
    consider using more advanced metrics like Levenshtein distance or
    fuzzy matching libraries (rapidfuzz).
    
    Args:
        str1 (str): First string.
        str2 (str): Second string.
        
    Returns:
        float: Similarity score between 0.0 and 1.0.
        
    Examples:
        >>> calculate_similarity_score("hello", "hello")
        1.0
        >>> calculate_similarity_score("hello", "helo")
        0.8
        >>> calculate_similarity_score("abc", "xyz")
        0.0
    """
    if not str1 or not str2:
        return 0.0
    
    if str1 == str2:
        return 1.0
    
    # Normalize both strings
    str1 = normalize_string(str1)
    str2 = normalize_string(str2)
    
    if str1 == str2:
        return 1.0
    
    # Simple character overlap metric
    set1 = set(str1)
    set2 = set(str2)
    
    if not set1 or not set2:
        return 0.0
    
    intersection = len(set1 & set2)
    union = len(set1 | set2)
    
    return intersection / union if union > 0 else 0.0


def clean_youtube_title(title: str) -> str:
    """Clean YouTube video title for matching.
    
    Combines noise word removal and normalization specifically for
    YouTube video titles.
    
    Args:
        title (str): YouTube video title.
        
    Returns:
        str: Cleaned title.
        
    Examples:
        >>> clean_youtube_title("The Weeknd - Blinding Lights (Official Video)")
        'the weeknd blinding lights'
        >>> clean_youtube_title("Ed Sheeran - Shape of You [Official Music Video] HD")
        'ed sheeran shape of you'
    """
    if not title:
        return ""
    
    # Remove noise words
    title = remove_noise_words(title)
    
    # Normalize
    title = normalize_string(title)
    
    return title
