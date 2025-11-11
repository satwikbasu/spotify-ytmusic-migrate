"""Unit tests for string normalization utilities.

This module tests all string normalization and cleaning functions
used for fuzzy matching between Spotify and YouTube Music.
"""

import pytest

from src.utils.string_utils import (
    normalize_string,
    remove_noise_words,
    sanitize_for_search,
    extract_featured_artists,
    normalize_for_comparison,
    calculate_similarity_score,
    clean_youtube_title
)


# ============================================================================
# normalize_string() Tests
# ============================================================================

def test_normalize_string_basic():
    """Test basic string normalization."""
    assert normalize_string("Hello World") == "hello world"
    assert normalize_string("UPPERCASE") == "uppercase"
    assert normalize_string("MiXeD CaSe") == "mixed case"


def test_normalize_string_accents():
    """Test accent removal from various languages."""
    # French
    assert normalize_string("Café Société") == "cafe societe"
    assert normalize_string("Français") == "francais"
    
    # Spanish
    assert normalize_string("José") == "jose"
    assert normalize_string("Niño") == "nino"
    assert normalize_string("Año") == "ano"
    
    # German
    assert normalize_string("Björk") == "bjork"
    assert normalize_string("Müller") == "muller"
    
    # Portuguese
    assert normalize_string("São Paulo") == "sao paulo"
    
    # Nordic
    assert normalize_string("Jóga") == "joga"
    assert normalize_string("Håkan") == "hakan"


def test_normalize_string_punctuation():
    """Test punctuation removal."""
    assert normalize_string("Hello, World!") == "hello world"
    assert normalize_string("What's up?") == "whats up"
    assert normalize_string("Test...") == "test"
    assert normalize_string("One-Two-Three") == "onetwothree"
    assert normalize_string("@#$%^&*()") == ""


def test_normalize_string_whitespace():
    """Test whitespace handling."""
    assert normalize_string("  Multiple   Spaces  ") == "multiple spaces"
    assert normalize_string("Tab\tSpace") == "tab space"
    assert normalize_string("New\nLine") == "new line"
    assert normalize_string("   ") == ""


def test_normalize_string_edge_cases():
    """Test edge cases."""
    assert normalize_string("") == ""
    assert normalize_string("   ") == ""
    assert normalize_string("123") == "123"
    assert normalize_string("a") == "a"


def test_unicode_characters():
    """Test that emojis and unicode characters are removed.
    
    Per test_spec.md requirement #9:
    Input: "🎵 Song Name 🎵"
    Expected: "song name" (emojis removed)
    """
    # Test emojis
    assert normalize_string("🎵 Song Name 🎵") == "song name"
    assert normalize_string("Artist 😊 Name") == "artist name"
    assert normalize_string("💿 Album Title 🎧") == "album title"
    
    # Test other unicode symbols
    assert normalize_string("Song ™ Name") == "song name"
    assert normalize_string("© Copyright ®") == "copyright"
    
    # Test mixed content
    assert normalize_string("🎵 Blinding Lights 💎 (Official)") == "blinding lights official"


# ============================================================================
# remove_noise_words() Tests
# ============================================================================

def test_remove_noise_words_official_video():
    """Test removal of 'Official Video' variants."""
    assert remove_noise_words("Song Name (Official Video)") == "Song Name"
    assert remove_noise_words("Song Name [Official Video]") == "Song Name"
    assert remove_noise_words("Song Name Official Video") == "Song Name"
    assert remove_noise_words("Song Name (official video)") == "Song Name"


def test_remove_noise_words_music_video():
    """Test removal of 'Official Music Video'."""
    assert remove_noise_words("Song (Official Music Video)") == "Song"
    assert remove_noise_words("Song [Official Music Video]") == "Song"
    # Should remove longer phrase first, not just "Official"
    assert "Music" not in remove_noise_words("Song Official Music Video")


def test_remove_noise_words_lyric_video():
    """Test removal of lyric video markers."""
    assert remove_noise_words("Song (Lyric Video)") == "Song"
    assert remove_noise_words("Song [Official Lyric Video]") == "Song"


def test_remove_noise_words_audio():
    """Test removal of audio markers."""
    assert remove_noise_words("Song (Official Audio)") == "Song"
    assert remove_noise_words("Song [Audio]") == "Song"


def test_remove_noise_words_quality_markers():
    """Test removal of quality markers."""
    assert remove_noise_words("Song (HD)") == "Song"
    assert remove_noise_words("Song [4K]") == "Song"
    assert remove_noise_words("Song HQ") == "Song"


def test_remove_noise_words_multiple():
    """Test removal of multiple noise words."""
    assert remove_noise_words("Song (Official Video) [HD]") == "Song"
    # The dash gets removed along with the noise words
    assert remove_noise_words("Song - Official Music Video (Explicit)") == "Song"


def test_remove_noise_words_empty_brackets():
    """Test cleanup of empty brackets after removal."""
    # After removing noise words, empty brackets should be removed
    result = remove_noise_words("Song (Official)")
    assert "(" not in result
    assert ")" not in result


def test_remove_noise_words_preserve_content():
    """Test that actual content is preserved."""
    assert remove_noise_words("Beautiful Song") == "Beautiful Song"
    assert remove_noise_words("My Track Name") == "My Track Name"


def test_remove_noise_words_empty():
    """Test remove_noise_words with empty input."""
    assert remove_noise_words("") == ""
    assert remove_noise_words(None) == ""


# ============================================================================
# sanitize_for_search() Tests
# ============================================================================

def test_sanitize_for_search_basic():
    """Test basic search query sanitization."""
    result = sanitize_for_search("Blinding Lights", ["The Weeknd"])
    assert result == "the weeknd blinding lights"


def test_sanitize_for_search_with_noise():
    """Test sanitization with noise words."""
    result = sanitize_for_search("Shape of You (Official Video)", ["Ed Sheeran"])
    assert result == "ed sheeran shape of you"
    assert "official" not in result
    assert "video" not in result


def test_sanitize_for_search_with_accents():
    """Test sanitization with accented characters."""
    result = sanitize_for_search("Café del Mar", ["Энергия"])
    # Should normalize Cyrillic and remove accents
    assert "cafe" in result
    assert "del" in result
    assert "mar" in result


def test_sanitize_for_search_multiple_artists():
    """Test that only first artist is used."""
    result = sanitize_for_search("Someone Like You", ["Adele", "Featured Artist"])
    assert "adele" in result
    assert "featured artist" not in result


def test_sanitize_for_search_no_artists():
    """Test sanitization with empty artists list."""
    result = sanitize_for_search("Track Name", [])
    assert result == "track name"


def test_sanitize_for_search_punctuation():
    """Test sanitization removes punctuation."""
    result = sanitize_for_search("What's Up?", ["4 Non Blondes"])
    assert "?" not in result
    assert "'" not in result


def test_sanitize_for_search_empty_track():
    """Test sanitization with empty track name."""
    assert sanitize_for_search("", ["Artist"]) == ""
    assert sanitize_for_search(None, ["Artist"]) == ""


# ============================================================================
# extract_featured_artists() Tests
# ============================================================================

def test_extract_featured_artists_feat():
    """Test extraction with 'feat.' pattern."""
    name, artists = extract_featured_artists("Levitating (feat. DaBaby)")
    assert name == "Levitating"
    assert "DaBaby" in artists


def test_extract_featured_artists_ft():
    """Test extraction with 'ft.' pattern."""
    name, artists = extract_featured_artists("Song Name (ft. Artist)")
    assert name == "Song Name"
    assert "Artist" in artists


def test_extract_featured_artists_with():
    """Test extraction with 'with' pattern."""
    name, artists = extract_featured_artists("Stay (with Justin Bieber)")
    assert name == "Stay"
    assert "Justin Bieber" in artists


def test_extract_featured_artists_multiple():
    """Test extraction of multiple featured artists."""
    name, artists = extract_featured_artists("Song (feat. Artist1, Artist2 & Artist3)")
    assert name == "Song"
    assert len(artists) == 3
    assert "Artist1" in artists
    assert "Artist2" in artists
    assert "Artist3" in artists


def test_extract_featured_artists_none():
    """Test extraction when no featured artists."""
    name, artists = extract_featured_artists("Normal Song Name")
    assert name == "Normal Song Name"
    assert len(artists) == 0


def test_extract_featured_artists_brackets():
    """Test extraction with square brackets."""
    name, artists = extract_featured_artists("Song [feat. Artist]")
    assert name == "Song"
    assert "Artist" in artists


def test_extract_featured_artists_featuring():
    """Test extraction with 'featuring' full word."""
    name, artists = extract_featured_artists("Song (featuring Artist Name)")
    assert name == "Song"
    assert "Artist Name" in artists


def test_extract_featured_artists_empty():
    """Test extraction with empty input."""
    name, artists = extract_featured_artists("")
    assert name == ""
    assert len(artists) == 0
    
    name, artists = extract_featured_artists(None)
    assert name == ""
    assert len(artists) == 0


# ============================================================================
# normalize_for_comparison() Tests
# ============================================================================

def test_normalize_for_comparison_basic():
    """Test aggressive normalization."""
    result = normalize_for_comparison("The Beatles - A Day in the Life")
    # "in" is only removed as a standalone word when surrounded by spaces
    # In "in the", only "the" gets removed, leaving "in"
    assert result == "beatles day in life"
    # "the" and "a" should be removed
    assert "the" not in result


def test_normalize_for_comparison_articles():
    """Test removal of articles."""
    result = normalize_for_comparison("The Song")
    assert "the" not in result
    
    result = normalize_for_comparison("A Song")
    assert result == "song"
    
    result = normalize_for_comparison("An Album")
    assert result == "album"


def test_normalize_for_comparison_numbers():
    """Test that numbers are preserved."""
    result = normalize_for_comparison("Song 2016")
    assert "2016" in result


def test_normalize_for_comparison_special_chars():
    """Test removal of special characters."""
    result = normalize_for_comparison("Song!@#$%Name")
    assert result == "songname"


def test_normalize_for_comparison_empty():
    """Test normalization with empty input."""
    assert normalize_for_comparison("") == ""
    assert normalize_for_comparison(None) == ""


# ============================================================================
# calculate_similarity_score() Tests
# ============================================================================

def test_similarity_score_identical():
    """Test similarity of identical strings."""
    assert calculate_similarity_score("hello", "hello") == 1.0
    assert calculate_similarity_score("Test", "test") == 1.0  # Case-insensitive


def test_similarity_score_different():
    """Test similarity of completely different strings."""
    score = calculate_similarity_score("abc", "xyz")
    assert score == 0.0


def test_similarity_score_similar():
    """Test similarity of similar strings."""
    # "hello" normalized = "hello", "helo" normalized = "helo"
    # Character overlap: h,e,l,o all present in both -> 100% overlap
    score = calculate_similarity_score("hello", "helo")
    assert score == 1.0  # All unique chars in both strings match


def test_similarity_score_empty():
    """Test similarity with empty strings."""
    assert calculate_similarity_score("", "test") == 0.0
    assert calculate_similarity_score("test", "") == 0.0
    assert calculate_similarity_score("", "") == 0.0
    assert calculate_similarity_score(None, "test") == 0.0
    assert calculate_similarity_score("test", None) == 0.0


def test_similarity_score_accents():
    """Test that accents are normalized before comparison."""
    score = calculate_similarity_score("café", "cafe")
    assert score == 1.0  # Should be identical after normalization


# ============================================================================
# clean_youtube_title() Tests
# ============================================================================

def test_clean_youtube_title_basic():
    """Test basic YouTube title cleaning."""
    result = clean_youtube_title("Artist - Song Name")
    assert result == "artist song name"


def test_clean_youtube_title_with_noise():
    """Test cleaning with official video markers."""
    result = clean_youtube_title("The Weeknd - Blinding Lights (Official Video)")
    assert result == "the weeknd blinding lights"
    assert "official" not in result


def test_clean_youtube_title_complex():
    """Test cleaning complex YouTube title."""
    result = clean_youtube_title("Ed Sheeran - Shape of You [Official Music Video] HD")
    assert result == "ed sheeran shape of you"
    assert "official" not in result
    assert "hd" not in result


def test_clean_youtube_title_lyric_video():
    """Test cleaning lyric video titles."""
    result = clean_youtube_title("Adele - Someone Like You (Official Lyric Video)")
    assert result == "adele someone like you"


def test_clean_youtube_title_empty():
    """Test cleaning empty title."""
    assert clean_youtube_title("") == ""


# ============================================================================
# Integration Tests
# ============================================================================

def test_full_matching_pipeline():
    """Test complete matching pipeline from Spotify to YouTube."""
    # Spotify track
    spotify_track = "Café Society"
    spotify_artists = ["José González"]
    
    # YouTube video title
    youtube_title = "José González - Café Society (Official Video) [HD]"
    
    # Create search query
    search_query = sanitize_for_search(spotify_track, spotify_artists)
    
    # Clean YouTube title
    clean_yt_title = clean_youtube_title(youtube_title)
    
    # Both should be very similar after processing
    assert "jose" in search_query
    assert "gonzalez" in search_query
    assert "cafe" in search_query
    assert "society" in search_query
    
    assert "jose" in clean_yt_title
    assert "gonzalez" in clean_yt_title
    assert "cafe" in clean_yt_title
    assert "society" in clean_yt_title
    
    # Calculate similarity
    score = calculate_similarity_score(search_query, clean_yt_title)
    assert score > 0.8  # Should be highly similar


def test_real_world_example_1():
    """Test real-world example: The Weeknd - Blinding Lights."""
    spotify_query = sanitize_for_search("Blinding Lights", ["The Weeknd"])
    youtube_title = clean_youtube_title("The Weeknd - Blinding Lights (Official Video)")
    
    assert spotify_query == "the weeknd blinding lights"
    assert youtube_title == "the weeknd blinding lights"


def test_real_world_example_2():
    """Test real-world example with featured artist."""
    # Spotify
    track_name, featured = extract_featured_artists("Levitating (feat. DaBaby)")
    all_artists = ["Dua Lipa"] + featured
    spotify_query = sanitize_for_search(track_name, all_artists)
    
    # YouTube
    youtube_title = clean_youtube_title("Dua Lipa - Levitating feat. DaBaby (Official Music Video)")
    
    assert "dua lipa" in spotify_query
    assert "levitating" in spotify_query
    assert "dua lipa" in youtube_title
    assert "levitating" in youtube_title


def test_real_world_example_3():
    """Test real-world example with special characters."""
    spotify_query = sanitize_for_search("What's Up?", ["4 Non Blondes"])
    youtube_title = clean_youtube_title("4 Non Blondes - What's Up (Official Video)")
    
    # Both should normalize to similar strings
    assert "4" in spotify_query
    assert "non" in spotify_query
    assert "blondes" in spotify_query
    assert "whats" in spotify_query
    assert "up" in spotify_query
