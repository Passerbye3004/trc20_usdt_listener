import requests
import time
import json
import os
from datetime import datetime, timedelta
import logging
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('transaction_monitor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class TronTransactionMonitor:
    def __init__(self):
        # Configuration - Set these values
        self.WALLET_ADDRESS = os.getenv('WALLET_ADDRESS', 'YOUR_WALLET_ADDRESS_HERE')
        self.TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')
        self.TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', 'YOUR_CHAT_ID_HERE')
        self.TRONSCAN_API_KEY = os.getenv('TRONSCAN_API_KEY', '')  # Optional but recommended
        self.INTERVAL = int(os.getenv("INTERVAL_SECOND",30))
        # API endpoints
        self.TRONSCAN_API_BASE = "https://apilist.tronscanapi.com/api"
        self.TELEGRAM_API_BASE = f"https://api.telegram.org/bot{self.TELEGRAM_BOT_TOKEN}"
        
        # Track processed transactions to avoid duplicates
        self.processed_transactions = set()
        self.last_check_time = datetime.now() - timedelta(minutes=10)  # Start from 5 minutes ago
        
        # Validate configuration
        self._validate_config()

    def _validate_config(self):
        """Validate that all required configuration is set"""
        if self.WALLET_ADDRESS == 'YOUR_WALLET_ADDRESS_HERE':
            raise ValueError("Please set WALLET_ADDRESS environment variable")
        if self.TELEGRAM_BOT_TOKEN == 'YOUR_BOT_TOKEN_HERE':
            raise ValueError("Please set TELEGRAM_BOT_TOKEN environment variable")
        if self.TELEGRAM_CHAT_ID == 'YOUR_CHAT_ID_HERE':
            raise ValueError("Please set TELEGRAM_CHAT_ID environment variable")
        
        logger.info(f"Monitoring wallet: {self.WALLET_ADDRESS}")
        logger.info(f"Telegram Chat ID: {self.TELEGRAM_CHAT_ID}")

    def get_transactions(self):
        """Fetch recent transactions from TronScan API"""
        try:
            url = f"{self.TRONSCAN_API_BASE}/transaction"
            params = {
                'sort': '-timestamp',
                'count': 'true',
                'limit': 50,  # Get last 50 transactions
                'start': 0,
                'address': self.WALLET_ADDRESS
            }
            
            headers = {}
            if self.TRONSCAN_API_KEY:
                headers['TRON-PRO-API-KEY'] = self.TRONSCAN_API_KEY
            
            response = requests.get(url, params=params, headers=headers, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            transactions = data.get('data', [])
            
            logger.info(f"Fetched {len(transactions)} transactions from TronScan")
            return transactions
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching transactions: {e}")
            return []
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing JSON response: {e}")
            return []

    def get_token_transfers(self):
        """Fetch TRC-20 token transfers (USDT and other popular tokens)"""
        all_transfers = []
        
        # Popular TRC-20 tokens to monitor
        TRC20_CONTRACTS = {
            "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t": "USDT",  # Tether USD
        #     "TEkxiTehnzSmSe2XqrBj4w32RUN966rdz8": "USDC",   # USD Coin  
        #     "TUpMhErZL2fhh4sVNULAbNKLokS4GjC1F4": "TUSD",   # TrueUSD
        #     "TLf2b2kPL7joeax6PmGZeQjEFnTEk8bsHH": "BTT",    # BitTorrent Token
        }
        
        try:
            for contract_address, symbol in TRC20_CONTRACTS.items():
                url = f"{self.TRONSCAN_API_BASE}/token_trc20/transfers-with-status"
                params = {
                    'limit': 50,  # Reduced limit per token to avoid too many requests
                    'start': 0,
                    'trc20Id': contract_address,
                    'address': self.WALLET_ADDRESS,
                    'direction':0
                }
                
                headers = {}
                if self.TRONSCAN_API_KEY:
                    headers['TRON-PRO-API-KEY'] = self.TRONSCAN_API_KEY
                
                response = requests.get(url, params=params, headers=headers, timeout=30)
                response.raise_for_status()
                
                data = response.json()
                transfers = data.get('data', [])
                
                # Add contract info to each transfer for easier processing
                for transfer in transfers:
                    transfer['_contract_symbol'] = symbol
                    transfer['_contract_address'] = contract_address
                
                all_transfers.extend(transfers)
                time.sleep(0.5)  # Small delay between requests to avoid rate limiting
            
            logger.info(f"Fetched {len(all_transfers)} total token transfers from TronScan")
            return all_transfers
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching token transfers: {e}")
            return []

    def send_telegram_message(self, message, parse_mode='HTML'):
        """Send message to Telegram"""
        try:
            url = f"{self.TELEGRAM_API_BASE}/sendMessage"
            data = {
                "chat_id": self.TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True
            }
            
            response = requests.post(url, data=data, timeout=30)
            response.raise_for_status()
            
            logger.info("Telegram notification sent successfully")
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error sending Telegram message: {e}")
            return None

    def format_transaction_message(self, tx):
        """Format transaction data into readable Telegram message"""
        try:
            tx_hash = tx.get('hash', 'N/A')
            timestamp = tx.get('timestamp', 0)
            block = tx.get('block', 'N/A')
            
            # Convert timestamp to readable format
            if timestamp:
                try:
                    dt = datetime.fromtimestamp(int(timestamp) / 1000)
                    time_str = dt.strftime('%Y-%m-%d %H:%M:%S UTC')
                except (ValueError, TypeError):
                    time_str = 'N/A'
            else:
                time_str = 'N/A'
            
            # Get transaction details
            from_addr = tx.get('ownerAddress', 'N/A')
            to_addr = tx.get('toAddress', 'N/A')
            raw_amount = tx.get('amount', 0)
            contract_type = tx.get('contractType', 'Unknown')
            
            # Safe amount conversion
            try:
                if isinstance(raw_amount, str):
                    amount = float(raw_amount)
                else:
                    amount = float(raw_amount) if raw_amount else 0
                amount_trx = amount / 1_000_000
            except (ValueError, TypeError):
                amount_trx = 0
                logger.warning(f"Could not parse amount: {raw_amount}")
            
            # Determine if incoming or outgoing
            direction = "📥 Incoming" if to_addr.lower() == self.WALLET_ADDRESS.lower() else "📤 Outgoing"
            
            message = f"🔔 <b>New TRX Transaction!</b>\n\n"
            message += f"{direction}\n"
            message += f"💰 <b>Amount:</b> {amount_trx:.6f} TRX\n"
            message += f"👤 <b>From:</b> <code>{from_addr}</code>\n"
            message += f"👤 <b>To:</b> <code>{to_addr}</code>\n"
            message += f"📝 <b>Type:</b> {contract_type}\n"
            message += f"🕒 <b>Time:</b> {time_str}\n"
            message += f"📦 <b>Block:</b> {block}\n"
            message += f"📋 <b>Hash:</b> <code>{tx_hash}</code>\n\n"
            message += f"🔍 <a href='https://tronscan.org/#/transaction/{tx_hash}'>View on TronScan</a>"
            
            return message
            
        except Exception as e:
            logger.error(f"Error formatting transaction message: {e}")
            logger.error(f"Transaction data: {json.dumps(tx, indent=2)}")
            return f"🔔 New transaction detected: {tx.get('hash', 'Unknown')}"

    def format_token_transfer_message(self, transfer):
        """Format token transfer data into readable Telegram message"""
        try:
            tx_hash = transfer.get('hash', 'N/A')
            timestamp = transfer.get('block_timestamp', 0)
            block = transfer.get('block', 'N/A')
            
            # Convert timestamp to readable format
            if timestamp:
                try:
                    dt = datetime.fromtimestamp(int(timestamp) / 1000)
                    time_str = dt.strftime('%Y-%m-%d %H:%M:%S UTC')
                except (ValueError, TypeError):
                    time_str = 'N/A'
            else:
                time_str = 'N/A'
            
            # Get transfer details from new API structure
            from_addr = transfer.get('from', 'N/A')
            to_addr = transfer.get('to', 'N/A')
            raw_amount = transfer.get('amount', 0)
            token_name = transfer.get('token_name', 'Unknown Token')
            decimals = transfer.get('decimals', 0)
            contract_address = transfer.get('contract_address', 'N/A')
            status = transfer.get('status', 0)
            direction = transfer.get('direction', 0)
            
            # Get token symbol from contract address or fallback
            contract_address = transfer.get('contract_address', 'N/A')
            token_symbol = transfer.get('_contract_symbol')  # Added by our code
            
            if not token_symbol:
                # Fallback to known contracts
                known_contracts = {
                    "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t": "USDT",
                    # "TEkxiTehnzSmSe2XqrBj4w32RUN966rdz8": "USDC",
                    # "TUpMhErZL2fhh4sVNULAbNKLokS4GjC1F4": "TUSD",
                    # "TLf2b2kPL7joeax6PmGZeQjEFnTEk8bsHH": "BTT"
                }
                token_symbol = known_contracts.get(contract_address, "UNK")
            
            # Safe amount conversion
            try:
                if isinstance(raw_amount, str):
                    amount = float(raw_amount)
                else:
                    amount = float(raw_amount) if raw_amount else 0
                    
                # Convert decimals safely
                if isinstance(decimals, str):
                    decimals = int(decimals)
                elif not isinstance(decimals, int):
                    decimals = 0
                    
                # Calculate actual amount
                actual_amount = amount / (10 ** decimals) if decimals > 0 else amount
                
            except (ValueError, TypeError) as e:
                logger.warning(f"Could not parse token amount: {raw_amount}, decimals: {decimals}, error: {e}")
                actual_amount = 0
            
            # Determine direction based on addresses and direction field
            if direction == 1:  # Outgoing
                direction_text = "📤 Sent"
            else:  # Incoming
                direction_text = "📥 Received"
            
            # Status text
            status_text = "✅ Success" if status == 0 else f"⚠️ Status: {status}"
            
            message = f"🪙 <b>New {token_symbol} Transfer!</b>\n\n"
            message += f"{direction_text}\n"
            message += f"💰 <b>Amount:</b> {actual_amount:,.6f} {token_symbol}\n"
            message += f"🏷️ <b>Token:</b> {token_name} ({token_symbol})\n"
            message += f"👤 <b>From:</b> <code>{from_addr}</code>\n"
            message += f"👤 <b>To:</b> <code>{to_addr}</code>\n"
            message += f"📋 <b>Status:</b> {status_text}\n"
            message += f"🕒 <b>Time:</b> {time_str}\n"
            message += f"📦 <b>Block:</b> {block}\n"
            message += f"📋 <b>Hash:</b> <code>{tx_hash}</code>\n\n"
            message += f"🔍 <a href='https://tronscan.org/#/transaction/{tx_hash}'>View on TronScan</a>"
            
            return message
            
        except Exception as e:
            logger.error(f"Error formatting token transfer message: {e}")
            logger.error(f"Transfer data: {json.dumps(transfer, indent=2)}")
            return f"🪙 New token transfer detected: {transfer.get('hash', 'Unknown')}"

    def is_new_transaction(self, tx_hash, timestamp):
        """Check if transaction is new (not processed before and within time window)"""
        if tx_hash in self.processed_transactions:
            return False
        
        # Check if transaction is newer than last check
        if timestamp:
            tx_time = datetime.fromtimestamp(timestamp / 1000)
            if tx_time <= self.last_check_time:
                return False
        
        return True

    def process_transactions(self):
        """Process and notify about new transactions"""
        logger.info("Checking for new transactions...")
        
        new_transactions_found = 0
        current_time = datetime.now()
        

        
        # Get token transfers
        transfers = self.get_token_transfers()
        for transfer in transfers:
            tx_hash = transfer.get('hash')
            timestamp = transfer.get('block_timestamp', 0)
            
            if tx_hash and self.is_new_transaction(tx_hash, timestamp):
                message = self.format_token_transfer_message(transfer)
                self.send_telegram_message(message)
                self.processed_transactions.add(tx_hash)
                new_transactions_found += 1
                time.sleep(1)  # Avoid rate limiting
        
        # Get TRX transactions
        transactions = self.get_transactions()
        for tx in transactions:
            tx_hash = tx.get('hash')
            timestamp = tx.get('timestamp', 0)
            
            if tx_hash and self.is_new_transaction(tx_hash, timestamp):
                message = self.format_transaction_message(tx)
                self.send_telegram_message(message)
                self.processed_transactions.add(tx_hash)
                new_transactions_found += 1
                time.sleep(1)  # Avoid rate limiting
        # Update last check time
        self.last_check_time = current_time
        
        # Clean up old processed transactions (keep only last 1000)
        if len(self.processed_transactions) > 1000:
            self.processed_transactions = set(list(self.processed_transactions)[-500:])
        
        if new_transactions_found > 0:
            logger.info(f"Found and processed {new_transactions_found} new transactions")
        else:
            logger.info("No new transactions found")

    def debug_transaction_data(self, tx):
        """Debug function to inspect transaction data structure"""
        logger.info("=== TRANSACTION DATA DEBUG ===")
        logger.info(f"Full transaction data: {json.dumps(tx, indent=2)}")
        
        # Check specific fields that might cause issues
        amount = tx.get('amount', 'NOT_FOUND')
        logger.info(f"Amount field: {amount} (type: {type(amount)})")
        
        timestamp = tx.get('timestamp', 'NOT_FOUND')
        logger.info(f"Timestamp field: {timestamp} (type: {type(timestamp)})")
        
        hash_field = tx.get('hash', 'NOT_FOUND')
        logger.info(f"Hash field: {hash_field} (type: {type(hash_field)})")
        
        logger.info("=== END DEBUG ===")

    def test_api_response(self):
        """Test function to check API response structure"""
        try:
            url = f"{self.TRONSCAN_API_BASE}/transaction"
            params = {
                'sort': '-timestamp',
                'limit': 1,  # Just get 1 transaction for testing
                'address': self.WALLET_ADDRESS
            }
            
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            logger.info("=== API RESPONSE TEST ===")
            logger.info(f"Response keys: {list(data.keys())}")
            
            transactions = data.get('data', [])
            if transactions:
                logger.info(f"First transaction keys: {list(transactions[0].keys())}")
                self.debug_transaction_data(transactions[0])
            else:
                logger.info("No transactions found in response")
                
            logger.info("=== END API TEST ===")
            
        except Exception as e:
            logger.error(f"API test failed: {e}")

    def send_startup_message(self):
        """Send a startup notification"""
        message = (
            f"🚀 <b>TronScan Monitor Started!</b>\n\n"
            f"👀 Monitoring wallet: <code>{self.WALLET_ADDRESS}</code>\n"
            f"⏰ Check interval: {self.INTERVAL} (seconds)\n"
            f"🕒 Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n"
            f"You will receive notifications for all incoming and outgoing transactions."
        )
        self.send_telegram_message(message)

    def run(self):
        """Main monitoring loop"""
        logger.info("Starting TronScan Transaction Monitor...")
        
        # Send startup notification
        self.send_startup_message()
        
        while True:
            try:
                self.process_transactions()
                logger.info("Waiting 60 seconds until next check...")
                time.sleep(self.INTERVAL)  # Wait 1 minute
                
            except KeyboardInterrupt:
                logger.info("Monitor stopped by user")
                break
            except Exception as e:
                logger.error(f"Unexpected error in main loop: {e}")
                time.sleep(self.INTERVAL)  # Wait before retrying

if __name__ == "__main__":
    monitor = TronTransactionMonitor()
    monitor.run()