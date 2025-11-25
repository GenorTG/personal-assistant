"""Debug script to test TTS settings endpoint."""
import httpx
import asyncio

async def test_tts_settings():
    """Test the TTS settings endpoint and print the full error."""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get("http://localhost:8000/api/voice/tts/settings")
            print(f"Status Code: {response.status_code}")
            print(f"Response: {response.json()}")
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_tts_settings())
