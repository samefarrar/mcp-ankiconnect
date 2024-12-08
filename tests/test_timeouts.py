import pytest
from unittest.mock import AsyncMock, patch
import httpx
import asyncio
from mcp_ankiconnect.server import AnkiConnectClient
from mcp_ankiconnect.config import TIMEOUTS

@pytest.mark.asyncio
async def test_client_timeout_configuration():
    """Test that AnkiConnectClient is configured with correct timeout values"""
    with patch('httpx.AsyncClient') as mock_client:
        client = AnkiConnectClient()
        
        # Verify timeout configuration
        mock_client.assert_called_once()
        timeout_arg = mock_client.call_args[1]['timeout']
        assert timeout_arg.connect == TIMEOUTS.connect
        assert timeout_arg.read == TIMEOUTS.read
        assert timeout_arg.write == TIMEOUTS.write

        await client.close()

@pytest.mark.asyncio
async def test_retry_on_timeout():
    """Test that operations retry on timeout"""
    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.aclose = AsyncMock()
        mock_client_class.return_value = mock_client
        
        # Configure mock to fail twice with timeout then succeed
        mock_response = AsyncMock()
        mock_response.json.return_value = {"result": ["Default"], "error": None}
        mock_response.raise_for_status = AsyncMock()
        
        mock_client.post.side_effect = [
            httpx.TimeoutException("Connection timed out"),
            httpx.TimeoutException("Connection timed out"),
            mock_response
        ]
        
        client = AnkiConnectClient()
        result = await client.deck_names()
        
        # Verify it was called 3 times
        assert mock_client.post.call_count == 3
        assert result == ["Default"]
        
        await client.close()

@pytest.mark.asyncio
async def test_retry_exhaustion():
    """Test that operations fail after max retries"""
    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value = mock_client
        
        # Configure mock to always timeout
        mock_client.post.side_effect = httpx.TimeoutException("Connection timed out")
        
        client = AnkiConnectClient()
        with pytest.raises(RuntimeError) as exc_info:
            await client.deck_names()
        
        # Verify it was called max_retries times
        assert mock_client.post.call_count == 3
        assert "failed after 3 attempts" in str(exc_info.value)
        
        await client.close()

@pytest.mark.asyncio
async def test_retry_backoff():
    """Test that retry backoff timing is correct"""
    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value = mock_client
        
        # Configure mock to always timeout
        mock_client.post.side_effect = httpx.TimeoutException("Connection timed out")
        
        client = AnkiConnectClient()
        start_time = asyncio.get_event_loop().time()
        
        with pytest.raises(RuntimeError):
            await client.deck_names()
            
        end_time = asyncio.get_event_loop().time()
        duration = end_time - start_time
        
        # With 3 retries and delays of 1, 2, 3 seconds
        # Total delay should be at least 6 seconds
        assert duration >= 6
        
        await client.close()

@pytest.mark.asyncio
async def test_timeout_error_message():
    """Test that timeout errors provide helpful messages"""
    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value = mock_client
        
        mock_client.post.side_effect = httpx.TimeoutException("Connection timed out")
        
        client = AnkiConnectClient()
        with pytest.raises(RuntimeError) as exc_info:
            await client.deck_names()
        
        error_msg = str(exc_info.value)
        assert "Unable to connect to Anki" in error_msg
        assert "ensure Anki is running" in error_msg
        assert "AnkiConnect plugin is installed" in error_msg
        
        await client.close()
