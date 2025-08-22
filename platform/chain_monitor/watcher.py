
import asyncio
import structlog
from typing import Dict, Any, Optional
from web3 import Web3
from datetime import datetime

from ..types import Event
from ..streaming import EventStream
from ..config import config
from ..rust_bindings import decode_transaction

logger = structlog.get_logger()


class ChainWatcher:
    """Monitors a blockchain for events and publishes them to the event stream."""

    def __init__(self, chain_id: int, event_stream: EventStream):
        self.chain_id = chain_id
        self.event_stream = event_stream
        self.w3 = Web3(Web3.HTTPProvider(self._get_rpc_url()))
        self._running = False
        self._poll_task: Optional[asyncio.Task] = None

    def _get_rpc_url(self) -> str:
        # In a real implementation, this would fetch the RPC URL from config based on chain_id
        return config.rpc_urls.get(self.chain_id, "")

    async def start(self):
        """Start the chain watcher."""
        self._running = True
        self._poll_task = asyncio.create_task(self._poll_for_events())
        logger.info("ChainWatcher started", chain_id=self.chain_id)

    async def stop(self):
        """Stop the chain watcher."""
        self._running = False
        if self._poll_task:
            self._poll_task.cancel()

    async def _poll_for_events(self):
        """Poll for new blocks and process events."""
        last_processed_block = await asyncio.to_thread(self.w3.eth.get_block_number) - 1

        while self._running:
            try:
                latest_block = await asyncio.to_thread(self.w3.eth.get_block_number)
                for block_number in range(last_processed_block + 1, latest_block + 1):
                    block = await asyncio.to_thread(self.w3.eth.get_block, block_number, full_transactions=True)
                    for tx in block.transactions:
                        from ..types.events import EventPayload, EventMetadata
                        class DecodedTxPayload(EventPayload):
                            def get_event_type(self) -> str: return "transaction.decoded"
                        
                        # Try to fetch raw RLP to leverage native decoder; fallback to web3 object
                        raw_hex = await asyncio.to_thread(self._try_get_raw_tx_hex, tx)
                        decoded_tx = decode_transaction(raw_hex if raw_hex else tx)

                        event = Event(
                            event_type="transaction.decoded",
                            aggregate_id=tx.hash,
                            aggregate_type="transaction",
                            aggregate_version=1,
                            business_timestamp=datetime.fromtimestamp(block.timestamp),
                            payload=DecodedTxPayload(**decoded_tx),
                            metadata=EventMetadata(source_service="ChainWatcher", source_version="1.0.0", additional_data={"chain_id": self.chain_id})
                        )
                        await self.event_stream.publish(f"transaction.decoded.{self.chain_id}", event.dict())
                    last_processed_block = block_number

                await asyncio.sleep(15)  # Poll every 15 seconds
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error polling for events", error=str(e))
                await asyncio.sleep(60)

    def _try_get_raw_tx_hex(self, tx: Any) -> Optional[str]:
        """Attempt to fetch raw RLP hex for a transaction, else None.
        Uses eth_getRawTransactionByHash if available.
        """
        try:
            tx_hash = tx.hash if hasattr(tx, "hash") else tx.get("hash")
            if tx_hash is None:
                return None
            raw = self.w3.eth.get_raw_transaction(tx_hash)
            # raw may be HexBytes; convert to hex string with 0x prefix
            if raw is None:
                return None
            if isinstance(raw, (bytes, bytearray)):
                return "0x" + raw.hex()
            # Web3's HexBytes has .hex()
            return raw.hex() if hasattr(raw, "hex") else str(raw)
        except Exception:
            return None
