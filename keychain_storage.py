"""
iOS Keychain secure storage for OAuth tokens.
Uses Security.framework via PyObjC.
"""

import platform
import json

IS_IOS = platform.system() == "Darwin"

if IS_IOS:
    try:
        from Foundation import NSMutableDictionary, NSData, NSString, NSUTF8StringEncoding
        import objc

        # Load Security framework
        Security = objc.ObjCLazyModule(
            "Security",
            frameworkIdentifier="com.apple.security",
            frameworkPath=objc.pathForFramework("/System/Library/Frameworks/Security.framework"),
            metadict={}
        )

        # Security constants
        kSecClass = Security.kSecClass
        kSecClassGenericPassword = Security.kSecClassGenericPassword
        kSecAttrService = Security.kSecAttrService
        kSecAttrAccount = Security.kSecAttrAccount
        kSecValueData = Security.kSecValueData
        kSecReturnData = Security.kSecReturnData
        kSecMatchLimit = Security.kSecMatchLimit
        kSecMatchLimitOne = Security.kSecMatchLimitOne
        kSecAttrAccessible = Security.kSecAttrAccessible
        kSecAttrAccessibleWhenUnlockedThisDeviceOnly = Security.kSecAttrAccessibleWhenUnlockedThisDeviceOnly

        KEYCHAIN_AVAILABLE = True
    except (ImportError, AttributeError):
        KEYCHAIN_AVAILABLE = False
else:
    KEYCHAIN_AVAILABLE = False

SERVICE_NAME = "com.snslocation.electricians-now.intuit-oauth"
ACCOUNT_NAME = "merchant-tokens"

# In-memory fallback for non-iOS platforms (testing only)
_memory_storage = {}


def save_to_keychain(data: dict) -> bool:
    """
    Save dictionary data to iOS Keychain.

    Args:
        data: Dictionary to store (will be JSON serialized)

    Returns:
        True if saved successfully, False otherwise
    """
    if not KEYCHAIN_AVAILABLE:
        # Fallback to memory storage for testing
        _memory_storage[ACCOUNT_NAME] = data
        return True

    try:
        json_data = json.dumps(data).encode('utf-8')
        ns_data = NSData.dataWithBytes_length_(json_data, len(json_data))

        # First try to delete any existing item
        delete_from_keychain()

        # Create query dictionary for adding new item
        query = NSMutableDictionary.dictionary()
        query[kSecClass] = kSecClassGenericPassword
        query[kSecAttrService] = SERVICE_NAME
        query[kSecAttrAccount] = ACCOUNT_NAME
        query[kSecValueData] = ns_data
        query[kSecAttrAccessible] = kSecAttrAccessibleWhenUnlockedThisDeviceOnly

        # Add to keychain
        status = Security.SecItemAdd(query, None)

        # errSecSuccess = 0
        return status == 0

    except Exception as e:
        print(f"Keychain save error: {e}")
        return False


def load_from_keychain() -> dict:
    """
    Load dictionary data from iOS Keychain.

    Returns:
        Dictionary if found, None otherwise
    """
    if not KEYCHAIN_AVAILABLE:
        # Fallback to memory storage for testing
        return _memory_storage.get(ACCOUNT_NAME)

    try:
        # Create query dictionary
        query = NSMutableDictionary.dictionary()
        query[kSecClass] = kSecClassGenericPassword
        query[kSecAttrService] = SERVICE_NAME
        query[kSecAttrAccount] = ACCOUNT_NAME
        query[kSecReturnData] = True
        query[kSecMatchLimit] = kSecMatchLimitOne

        # Query keychain
        result = []
        status = Security.SecItemCopyMatching(query, result)

        # errSecSuccess = 0
        if status == 0 and result:
            ns_data = result[0]
            json_bytes = bytes(ns_data)
            return json.loads(json_bytes.decode('utf-8'))

        return None

    except Exception as e:
        print(f"Keychain load error: {e}")
        return None


def delete_from_keychain() -> bool:
    """
    Delete data from iOS Keychain.

    Returns:
        True if deleted (or didn't exist), False on error
    """
    if not KEYCHAIN_AVAILABLE:
        # Fallback to memory storage for testing
        _memory_storage.pop(ACCOUNT_NAME, None)
        return True

    try:
        # Create query dictionary
        query = NSMutableDictionary.dictionary()
        query[kSecClass] = kSecClassGenericPassword
        query[kSecAttrService] = SERVICE_NAME
        query[kSecAttrAccount] = ACCOUNT_NAME

        # Delete from keychain
        status = Security.SecItemDelete(query)

        # errSecSuccess = 0, errSecItemNotFound = -25300
        return status in (0, -25300)

    except Exception as e:
        print(f"Keychain delete error: {e}")
        return False
