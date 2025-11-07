"""Token Encryption Utilities Module.

This module provides utilities for encrypting and decrypting sensitive data
such as OAuth tokens and credentials using Fernet symmetric encryption.

Fernet guarantees that encrypted data cannot be manipulated or read without the key.
It uses AES 128 encryption in CBC mode with PKCS7 padding, and HMAC using SHA256 for authentication.
"""

import os
import json
from typing import Dict, Any

from cryptography.fernet import Fernet, InvalidToken


# Default path for the master encryption key
DEFAULT_KEY_DIR = os.path.expanduser("~/.playlist_migrator")
DEFAULT_KEY_PATH = os.path.join(DEFAULT_KEY_DIR, "master.key")


def generate_key() -> bytes:
    """Generate a new Fernet encryption key.
    
    Creates a new random 32-byte (256-bit) encryption key suitable for
    Fernet symmetric encryption. This key should be kept secret and stored
    securely.
    
    Returns:
        bytes: A new Fernet encryption key (URL-safe base64-encoded 32 bytes).
        
    Example:
        >>> key = generate_key()
        >>> len(key)
        44  # Base64-encoded 32 bytes
    """
    return Fernet.generate_key()


def save_key(key: bytes, key_path: str) -> None:
    """Save an encryption key to a file.
    
    Writes the encryption key to the specified file path. Creates parent
    directories if they don't exist. The file is created with restricted
    permissions (0o600 on Unix-like systems) for security.
    
    Args:
        key (bytes): The encryption key to save.
        key_path (str): Path where the key should be saved. Supports ~ for home directory.
        
    Raises:
        IOError: If the key cannot be written to the file.
        OSError: If parent directories cannot be created.
        
    Example:
        >>> key = generate_key()
        >>> save_key(key, "~/.playlist_migrator/master.key")
    """
    try:
        # Expand user home directory if present
        expanded_path = os.path.expanduser(key_path)
        
        # Create parent directories if they don't exist
        parent_dir = os.path.dirname(expanded_path)
        if parent_dir and not os.path.exists(parent_dir):
            os.makedirs(parent_dir, mode=0o700)
            print(f"Created directory: {parent_dir}")
        
        # Write key to file
        with open(expanded_path, 'wb') as key_file:
            key_file.write(key)
        
        # Set restrictive file permissions (owner read/write only)
        # This only works on Unix-like systems; Windows handles permissions differently
        try:
            os.chmod(expanded_path, 0o600)
        except (OSError, AttributeError):
            # Windows doesn't support chmod in the same way
            pass
        
        print(f"Encryption key saved to: {expanded_path}")
        
    except IOError as e:
        raise IOError(f"Failed to save encryption key to {key_path}: {str(e)}") from e
    except OSError as e:
        raise OSError(f"Failed to create directory for encryption key: {str(e)}") from e


def load_key(key_path: str) -> bytes:
    """Load an encryption key from a file.
    
    Reads the encryption key from the specified file path. The path can
    include ~ to reference the user's home directory.
    
    Args:
        key_path (str): Path to the key file. Supports ~ for home directory.
        
    Returns:
        bytes: The encryption key read from the file.
        
    Raises:
        FileNotFoundError: If the key file doesn't exist.
        IOError: If the key cannot be read from the file.
        
    Example:
        >>> key = load_key("~/.playlist_migrator/master.key")
    """
    expanded_path = os.path.expanduser(key_path)
    
    if not os.path.exists(expanded_path):
        raise FileNotFoundError(
            f"Encryption key not found at: {expanded_path}. "
            f"Please generate a new key using generate_key() and save_key()."
        )
    
    try:
        with open(expanded_path, 'rb') as key_file:
            key = key_file.read()
        
        if not key:
            raise IOError(f"Encryption key file is empty: {expanded_path}")
        
        return key
        
    except IOError as e:
        raise IOError(f"Failed to load encryption key from {key_path}: {str(e)}") from e


def encrypt_data(data: str, key: bytes) -> bytes:
    """Encrypt string data using Fernet symmetric encryption.
    
    Encrypts the provided string data using the Fernet cipher with the given key.
    The data is first encoded to UTF-8 bytes before encryption.
    
    Args:
        data (str): The string data to encrypt.
        key (bytes): The Fernet encryption key.
        
    Returns:
        bytes: The encrypted data as bytes (URL-safe base64-encoded).
        
    Raises:
        ValueError: If the key is invalid or data cannot be encrypted.
        
    Example:
        >>> key = generate_key()
        >>> encrypted = encrypt_data("sensitive data", key)
    """
    try:
        # Create Fernet cipher instance
        cipher = Fernet(key)
        
        # Encode string to bytes and encrypt
        encrypted_bytes = cipher.encrypt(data.encode('utf-8'))
        
        return encrypted_bytes
        
    except Exception as e:
        raise ValueError(f"Failed to encrypt data: {str(e)}") from e


def decrypt_data(encrypted_data: bytes, key: bytes) -> str:
    """Decrypt bytes using Fernet symmetric encryption.
    
    Decrypts the provided encrypted bytes using the Fernet cipher with the given key.
    The decrypted bytes are decoded from UTF-8 to a string.
    
    Args:
        encrypted_data (bytes): The encrypted data to decrypt.
        key (bytes): The Fernet encryption key.
        
    Returns:
        str: The decrypted data as a string.
        
    Raises:
        InvalidToken: If the data cannot be decrypted (wrong key or corrupted data).
        ValueError: If the decrypted data cannot be decoded as UTF-8.
        
    Example:
        >>> key = generate_key()
        >>> encrypted = encrypt_data("sensitive data", key)
        >>> original = decrypt_data(encrypted, key)
    """
    try:
        # Create Fernet cipher instance
        cipher = Fernet(key)
        
        # Decrypt and decode to string
        decrypted_bytes = cipher.decrypt(encrypted_data)
        decrypted_string = decrypted_bytes.decode('utf-8')
        
        return decrypted_string
        
    except InvalidToken as e:
        raise InvalidToken(
            "Failed to decrypt data. The encryption key may be incorrect or the data may be corrupted."
        ) from e
    except UnicodeDecodeError as e:
        raise ValueError(f"Decrypted data is not valid UTF-8: {str(e)}") from e


def encrypt_json_file(file_path: str, key: bytes) -> None:
    """Encrypt a JSON file and save as an encrypted file.
    
    Reads a JSON file, encrypts its contents, and saves the encrypted data
    to a new file with a .enc extension. The original unencrypted file is
    deleted after successful encryption for security.
    
    Process:
    1. Read and parse JSON file
    2. Convert to JSON string
    3. Encrypt the string
    4. Write encrypted data to .enc file
    5. Delete original file
    
    Args:
        file_path (str): Path to the JSON file to encrypt. Supports ~ for home directory.
        key (bytes): The Fernet encryption key.
        
    Raises:
        FileNotFoundError: If the source file doesn't exist.
        json.JSONDecodeError: If the file is not valid JSON.
        IOError: If file operations fail.
        
    Example:
        >>> key = load_key("~/.playlist_migrator/master.key")
        >>> encrypt_json_file("~/youtube_oauth.json", key)
        # Creates ~/youtube_oauth.json.enc and deletes ~/youtube_oauth.json
    """
    expanded_path = os.path.expanduser(file_path)
    encrypted_path = f"{expanded_path}.enc"
    
    if not os.path.exists(expanded_path):
        raise FileNotFoundError(f"File not found: {expanded_path}")
    
    try:
        # Step 1: Read and parse JSON file
        with open(expanded_path, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
        
        # Step 2: Convert to JSON string
        json_string = json.dumps(json_data, indent=2)
        
        # Step 3: Encrypt the string
        encrypted_data = encrypt_data(json_string, key)
        
        # Step 4: Write encrypted data to .enc file
        with open(encrypted_path, 'wb') as f:
            f.write(encrypted_data)
        
        print(f"Encrypted file created: {encrypted_path}")
        
        # Step 5: Delete original file for security
        os.remove(expanded_path)
        print(f"Original file deleted: {expanded_path}")
        
    except json.JSONDecodeError as e:
        raise json.JSONDecodeError(
            f"Invalid JSON in file {file_path}: {e.msg}",
            e.doc,
            e.pos
        ) from e
    except IOError as e:
        raise IOError(f"Failed to encrypt file {file_path}: {str(e)}") from e
    except Exception as e:
        # Clean up encrypted file if something went wrong after creation
        if os.path.exists(encrypted_path):
            try:
                os.remove(encrypted_path)
            except OSError:
                pass
        raise IOError(f"Unexpected error encrypting file {file_path}: {str(e)}") from e


def decrypt_json_file(encrypted_path: str, key: bytes) -> Dict[str, Any]:
    """Decrypt an encrypted file and return the JSON data.
    
    Reads an encrypted file (typically with .enc extension), decrypts its contents,
    and parses the decrypted data as JSON.
    
    Process:
    1. Read encrypted file
    2. Decrypt the data
    3. Parse decrypted string as JSON
    4. Return dictionary
    
    Args:
        encrypted_path (str): Path to the encrypted file. Supports ~ for home directory.
        key (bytes): The Fernet encryption key.
        
    Returns:
        Dict[str, Any]: The decrypted JSON data as a dictionary.
        
    Raises:
        FileNotFoundError: If the encrypted file doesn't exist.
        InvalidToken: If decryption fails (wrong key or corrupted data).
        json.JSONDecodeError: If the decrypted data is not valid JSON.
        IOError: If file operations fail.
        
    Example:
        >>> key = load_key("~/.playlist_migrator/master.key")
        >>> data = decrypt_json_file("~/youtube_oauth.json.enc", key)
        >>> print(data['access_token'])
    """
    expanded_path = os.path.expanduser(encrypted_path)
    
    if not os.path.exists(expanded_path):
        raise FileNotFoundError(f"Encrypted file not found: {expanded_path}")
    
    try:
        # Step 1: Read encrypted file
        with open(expanded_path, 'rb') as f:
            encrypted_data = f.read()
        
        if not encrypted_data:
            raise IOError(f"Encrypted file is empty: {expanded_path}")
        
        # Step 2: Decrypt the data
        decrypted_string = decrypt_data(encrypted_data, key)
        
        # Step 3: Parse as JSON
        json_data = json.loads(decrypted_string)
        
        return json_data
        
    except InvalidToken:
        raise  # Re-raise InvalidToken as-is with original message
    except json.JSONDecodeError as e:
        raise json.JSONDecodeError(
            f"Decrypted data from {encrypted_path} is not valid JSON: {e.msg}",
            e.doc,
            e.pos
        ) from e
    except IOError as e:
        raise IOError(f"Failed to decrypt file {encrypted_path}: {str(e)}") from e


def ensure_master_key(key_path: str = DEFAULT_KEY_PATH) -> bytes:
    """Ensure a master encryption key exists, creating one if necessary.
    
    Checks if a master key exists at the specified path. If not, generates
    a new key and saves it. Returns the key (either loaded or newly created).
    
    Args:
        key_path (str): Path to the master key file. Defaults to ~/.playlist_migrator/master.key.
        
    Returns:
        bytes: The master encryption key.
        
    Example:
        >>> key = ensure_master_key()
        # First run: Generates and saves new key
        # Subsequent runs: Loads existing key
    """
    try:
        # Try to load existing key
        key = load_key(key_path)
        print(f"Loaded existing master key from: {key_path}")
        return key
    except FileNotFoundError:
        # No key exists, generate new one
        print("No master key found. Generating new encryption key...")
        key = generate_key()
        save_key(key, key_path)
        print("Master key generated and saved successfully.")
        return key
