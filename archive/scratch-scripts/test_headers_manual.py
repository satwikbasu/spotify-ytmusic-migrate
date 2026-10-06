"""
Test YouTube Music API with manually copied headers
"""
from ytmusicapi import YTMusic

# Headers copied from browser
headers_raw = """POST /youtubei/v1/browse?prettyPrint=false HTTP/3
Host: music.youtube.com
User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:145.0) Gecko/20100101 Firefox/145.0
Accept: */*
Accept-Language: en-US,en;q=0.5
Accept-Encoding: gzip, deflate, br, zstd
Referer: https://music.youtube.com/library
Content-Type: application/json
X-Goog-Visitor-Id: CgtsakV3YkpUdWNySSil5tbIBjIKCgJJThIEGgAgQQ%3D%3D
X-Youtube-Bootstrap-Logged-In: true
X-Youtube-Client-Name: 67
X-Youtube-Client-Version: 1.20251110.03.00
Authorization: SAPISIDHASH 1763029833_3471308993d5eba5bdb34a4c71a7976c411059b0_u SAPISID1PHASH 1763029833_3471308993d5eba5bdb34a4c71a7976c411059b0_u SAPISID3PHASH 1763029833_3471308993d5eba5bdb34a4c71a7976c411059b0_u
X-Goog-AuthUser: 0
X-Origin: https://music.youtube.com
Content-Length: 2649
Origin: https://music.youtube.com
Alt-Used: music.youtube.com
Connection: keep-alive
Cookie: __Secure-1PSIDTS=sidts-CjUBwQ9iI_fvKTV_D3yrKnB3gI09GwhD-dllviI8EyttqjOcV1Jhs4-IYicGvTH_erRyeV3nMxAA; __Secure-3PSIDTS=sidts-CjUBwQ9iI_fvKTV_D3yrKnB3gI09GwhD-dllviI8EyttqjOcV1Jhs4-IYicGvTH_erRyeV3nMxAA; HSID=Ay9BD6p6r60vpqCeY; SSID=AaCogHKie9I7uUmwq; APISID=WA7l7S9kII_5p3-u/Ar-l4Sq-QSHcIkZbz; SAPISID=Ctr6mBDV97_qyq8D/AO6d0ixESBHO36Zu7; __Secure-1PAPISID=Ctr6mBDV97_qyq8D/AO6d0ixESBHO36Zu7; __Secure-3PAPISID=Ctr6mBDV97_qyq8D/AO6d0ixESBHO36Zu7; SID=g.a0003QhNKyEegXUBYAopWpQ2G-jXkjCdJM67h6b4lvQ7LOQ5OKmAzR0nxZWxitn3IKDmXLBueAACgYKAc8SARQSFQHGX2MivMAcnWBLNBoh6QAwHIhk8BoVAUF8yKoSO9JzQpZljIAtWI3pXtv40076; __Secure-1PSID=g.a0003QhNKyEegXUBYAopWpQ2G-jXkjCdJM67h6b4lvQ7LOQ5OKmAmxCObu9G1i_JkqttC8oB5QACgYKAc0SARQSFQHGX2MiIJIqaiFEuMvcX6Twdo385BoVAUF8yKrM8flFBiAYEj5IEVJYkryW0076; __Secure-3PSID=g.a0003QhNKyEegXUBYAopWpQ2G-jXkjCdJM67h6b4lvQ7LOQ5OKmAaGp9DocAvbZocz1s7HqmzQACgYKAawSARQSFQHGX2Mi-QgC30H4hY7Ids1EvDFvghoVAUF8yKqmzOjsAkZxc9LPKOaWxiM10076; VISITOR_INFO1_LIVE=ljEwbJTucrI; VISITOR_PRIVACY_METADATA=CgJJThIEGgAgQQ%3D%3D; __Secure-ROLLOUT_TOKEN=CJuxqrGq07XXQBDm25LOx5iOAxiD4Y_jtuyQAw%3D%3D; SIDCC=AKEyXzU1JyYZx006IC3jH_VW43cSFi-lpCxkkyGLfLsICmOBYlfr7d7qqFzrOo1nohkM3zig5jc; __Secure-1PSIDCC=AKEyXzU3-x7nQIawM-fPISVCyRJ2RRwTq2dv9rMSQMz3gvyVfkKsK6_SGLprcuV-TsvWJWW1Ox0; __Secure-3PSIDCC=AKEyXzXWqsMNpCUK2YBxyMesDccIFLsZvpUQ9QWYD368t_yDNFr8tiSMtwsjIuV80jG3jfuFRQ; PREF=f6=40000000&tz=Asia.Kolkata&f7=100; LOGIN_INFO=AFmmF2swRAIgIu1yF5iMgTp0sZ407fpMKqSOz_LJeuTMaJjpXoK02ZwCIDqxGdIPlatGCx7vnievHWhfmcWCtFbYK-9ohFHHTTMe:QUQ3MjNmemN1Wkx6NElfSzFVb19VTkVGeWl6Z0Y1eDlzZWs4UTVuQ3lRa1JQNlp4cmNCcFRLZDVWb05KT1hWOF9VUUVtczZ1MFlmVzdTZWlpVFFpNzI3eHAzdm16a0RpMmNzMWQyRndhV1EtSlpRd19rMkM3V0Z3clhxcWhmcGhiTm04N2dmc2xvVGdULTJEN1lucklPY040UHBtSmRYYWFB; __Secure-ROLLOUT_TOKEN=CKXy5ZTNl_316wEQ8qrTk6mAkAMYvODFk4ODkAM%3D; YSC=nyo2ELQ9XUc
Sec-Fetch-Dest: empty
Sec-Fetch-Mode: same-origin
Sec-Fetch-Site: same-origin
Priority: u=4
Pragma: no-cache
Cache-Control: no-cache
TE: trailers"""

def test_manual_headers():
    try:
        print("Testing headers copied from browser...")
        print(f"Logged in status: {('X-Youtube-Bootstrap-Logged-In: true' in headers_raw) or 'false'}")
        print()
        
        # Create headers.json from the raw headers
        from ytmusicapi.auth.browser import setup_browser
        
        try:
            setup_browser("headers.json", headers_raw)
            print("✅ Headers file created successfully\n")
        except Exception as e:
            print(f"❌ Failed to create headers file: {e}")
            print("\nNote: Headers show 'X-Youtube-Bootstrap-Logged-In: false'")
            print("This means you're NOT logged in to YouTube Music.\n")
            return
        
        # Test the authentication
        print("Testing YouTube Music API...")
        yt = YTMusic("headers.json")
        
        # Test 1: Search (should work even without login)
        print("Test 1: search() - Should work")
        results = yt.search("test", limit=1)
        print(f"✅ Search works: Found {len(results)} results\n")
        
        # Test 2: Get library playlists (requires login)
        print("Test 2: get_library_playlists() - Requires login")
        try:
            playlists = yt.get_library_playlists(limit=5)
            print(f"✅ Library playlists work: Found {len(playlists)} playlists")
            print("✅ You ARE logged in and authentication works!\n")
        except Exception as e:
            print(f"❌ Failed: {e}")
            print("❌ You are NOT logged in to YouTube Music\n")
        
        # Test 3: Get account info (requires login)
        print("Test 3: get_account_info() - Requires login")
        try:
            account = yt.get_account_info()
            print(f"✅ Account info works: {account.get('accountName', 'Unknown')}")
            print("✅ Full authentication confirmed!\n")
        except Exception as e:
            print(f"❌ Failed: {e}\n")
        
        print("=" * 60)
        print("IMPORTANT:")
        print("Your headers show 'X-Youtube-Bootstrap-Logged-In: false'")
        print("You need to be LOGGED IN to YouTube Music first!")
        print("=" * 60)
        
    except Exception as e:
        print(f"❌ Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_manual_headers()
