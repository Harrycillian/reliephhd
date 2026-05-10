import json
import hashlib
import time
import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from web3 import Web3
from eth_account import Account
from eth_account.messages import encode_defunct
import requests
import base64
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import constant_time

class BlockchainManager:
    """Manages blockchain operations for ReliePH platform"""
    
    def __init__(self, rpc_url: str = None, private_key: str = None, donation_contract_address: str = None, fundraiser_contract_address: str = None):
        self.rpc_url = rpc_url or os.getenv('INFURA_URL')
        self.donation_contract_address = donation_contract_address or os.getenv('DONATION_CONTRACT_ADDRESS')
        self.fundraiser_contract_address = fundraiser_contract_address or os.getenv('FUNDRAISER_CONTRACT_ADDRESS')
        
        if not self.rpc_url:
            raise ValueError("RPC URL is required. Set INFURA_URL environment variable.")
        
        self.w3 = Web3(Web3.HTTPProvider(self.rpc_url))
        
        if self.donation_contract_address:
            try:
                self.donation_contract_address = self.w3.to_checksum_address(self.donation_contract_address)
            except Exception as e:
                print(f"Warning: Invalid donation contract address: {e}")
                self.donation_contract_address = None
        
        if self.fundraiser_contract_address:
            try:
                self.fundraiser_contract_address = self.w3.to_checksum_address(self.fundraiser_contract_address)
            except Exception as e:
                print(f"Warning: Invalid fundraiser contract address: {e}")
                self.fundraiser_contract_address = None
        
        print(f"🔑 Initializing blockchain account...")
        if private_key:
            self.account = Account.from_key(private_key)
            self.wallet_address = self.account.address
            print(f"✅ Account loaded from provided private key: {self.wallet_address}")
        else:
            env_private_key = os.getenv('PRIVATE_KEY')
            if env_private_key:
                self.account = Account.from_key(env_private_key)
                self.wallet_address = self.account.address
                print(f"✅ Account loaded from environment: {self.wallet_address}")
            else:
                self.account = Account.create()
                self.wallet_address = self.account.address
                print(f"⚠️  Generated new wallet for demo: {self.wallet_address}")
                print(f"Private key: {self.account.key.hex()}")
        
        print(f"✅ Account initialized successfully")
        print(f"   Address: {self.wallet_address}")
        print(f"   Key type: {type(self.account.key)}")
        
        self.donation_contract_abi = self._load_contract_abi('DonationContract.json')
        self.fundraiser_contract_abi = self._load_contract_abi('FundraiserContract.json')
        
        self.donation_contract = None
        self.fundraiser_contract = None
        
        if self.donation_contract_address and self.donation_contract_abi:
            self.donation_contract = self.w3.eth.contract(
                address=self.donation_contract_address,
                abi=self.donation_contract_abi
            )
        
        if self.fundraiser_contract_address and self.fundraiser_contract_abi:
            self.fundraiser_contract = self.w3.eth.contract(
                address=self.fundraiser_contract_address,
                abi=self.fundraiser_contract_abi
            )
    
    def _load_contract_abi(self, filename: str) -> List[Dict]:
        """Load contract ABI from JSON file"""
        try:
            with open(filename, 'r') as f:
                abi_data = json.load(f)
                # If the file contains the ABI directly
                if isinstance(abi_data, list):
                    return abi_data
                # If the file contains the ABI in an 'abi' field
                elif isinstance(abi_data, dict) and 'abi' in abi_data:
                    return abi_data['abi']
                else:
                    raise ValueError(f"Invalid ABI format in {filename}")
        except FileNotFoundError:
            print(f"Warning: ABI file {filename} not found. Using empty ABI.")
            return []
        except json.JSONDecodeError as e:
            print(f"Error parsing ABI file {filename}: {e}")
            return []
        except Exception as e:
            print(f"Error loading ABI file {filename}: {e}")
            return []
    
    def is_connected(self) -> bool:
        """Check if connected to blockchain network"""
        try:
            return self.w3.is_connected()
        except Exception:
            return False
    
    def get_balance(self, address: str = None) -> int:
        """Get ETH balance of an address"""
        if address is None:
            address = self.wallet_address
        
        try:
            balance_wei = self.w3.eth.get_balance(address)
            return self.w3.from_wei(balance_wei, 'ether')
        except Exception as e:
            print(f"Error getting balance: {e}")
            return 0
    
    def record_donation(self, fundraiser_id: int, donor_address: str, amount: float, 
                        reference_number: str) -> Dict:
        """
        Record a donation on the blockchain
        
        Args:
            fundraiser_id: ID of the fundraiser
            donor_address: Ethereum address of the donor
            amount: Donation amount in ETH
            reference_number: Reference number from the platform
            
        Returns:
            Dict containing transaction details
        """
        try:
            if not self.is_connected():
                raise Exception("Not connected to blockchain network")
            
            if not self.donation_contract:
                raise Exception("Donation contract not initialized")
            
            # Convert donor address to checksum format
            donor_address = self.w3.to_checksum_address(donor_address)
            
            # Convert amount to wei
            amount_wei = self.w3.to_wei(amount, 'ether')
            
            # Build transaction
            print(f"🔨 Building transaction for donation...")
            print(f"   Donor: {donor_address}")
            print(f"   Amount: {amount} ETH ({amount_wei} wei)")
            print(f"   Fundraiser ID: {fundraiser_id}")
            print(f"   Reference: {reference_number}")
            
            # Prepare contract function
            fn = self.donation_contract.functions.createDonation(
                donor_address,
                amount_wei,
                fundraiser_id,
                "blockchain",
                reference_number
            )

            # Estimate gas (try different method names depending on web3 version)
            gas_estimate = None
            try:
                gas_estimate = fn.estimateGas({'from': self.wallet_address})
            except Exception:
                try:
                    gas_estimate = fn.estimate_gas({'from': self.wallet_address})
                except Exception as e:
                    print(f"Warning: gas estimate failed, falling back to default: {e}")

            # Decide gas limit: use estimate + buffer, or a sensible default
            if gas_estimate and isinstance(gas_estimate, int) and gas_estimate > 0:
                gas_limit = max(gas_estimate + 20000, int(gas_estimate * 1.3))
            else:
                gas_limit = 300000

            nonce = self.w3.eth.get_transaction_count(self.wallet_address)
            transaction = fn.build_transaction({
                'from': self.wallet_address,
                'gas': gas_limit,
                'gasPrice': self.w3.eth.gas_price,
                'nonce': nonce,
            })
            
            print(f"✅ Transaction built successfully")
            print(f"   Gas: {transaction.get('gas', 'N/A')}")
            print(f"   Gas Price: {transaction.get('gasPrice', 'N/A')}")
            print(f"   Nonce: {transaction.get('nonce', 'N/A')}")
            
            # Sign transaction
            try:
                signed_txn = self.w3.eth.account.sign_transaction(transaction, self.account.key)
                print(f"✅ Transaction signed successfully")
            except Exception as e:
                print(f"❌ Error signing transaction: {e}")
                raise e
            
            # Send transaction (handle different eth_account versions)
            attempt = 0
            max_attempts = 2
            last_exception = None
            while attempt < max_attempts:
                try:
                    # Sign transaction
                    signed_txn = self.w3.eth.account.sign_transaction(transaction, self.account.key)

                    # Extract raw transaction bytes (handle attribute differences)
                    try:
                        raw_tx = signed_txn.raw_transaction
                    except AttributeError:
                        raw_tx = signed_txn.rawTransaction

                    tx_hash = self.w3.eth.send_raw_transaction(raw_tx)
                    print(tx_hash)
                    print(f"✅ Transaction sent successfully: {tx_hash.hex()}")

                    # Wait for transaction receipt
                    tx_receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
                    break

                except Exception as send_err:
                    last_exception = send_err
                    err_text = str(send_err).lower()
                    print(f"⚠️ Transaction send attempt {attempt+1} failed: {send_err}")

                    # If error indicates out-of-gas, try increasing gas and retry
                    if 'out of gas' in err_text or 'intrinsic gas' in err_text or 'gas required exceeds allowance' in err_text:
                        # increase gas limit and rebuild transaction
                        gas_limit = int(gas_limit * 1.8) + 10000
                        print(f"🔧 Increasing gas limit and retrying: new gas_limit={gas_limit}")
                        nonce = self.w3.eth.get_transaction_count(self.wallet_address)
                        transaction['gas'] = gas_limit
                        transaction['nonce'] = nonce
                        attempt += 1
                        continue
                    else:
                        # Non gas-related error — rethrow
                        raise send_err

            else:
                # If we exit loop without break, raise last exception
                raise last_exception
            
            # Get the transaction hash from the event
            event_logs = self.donation_contract.events.DonationCreated().process_receipt(tx_receipt)
            if event_logs:
                # Use the transaction hash from the receipt since the event might not have transactionHash
                blockchain_tx_hash = tx_hash.hex()
            else:
                blockchain_tx_hash = tx_hash.hex()
            
            return {
                'success': True,
                'transaction_hash': blockchain_tx_hash,
                'block_number': tx_receipt.blockNumber,
                'gas_used': tx_receipt.gasUsed,
                'status': 'success'
            }
            
        except Exception as e:
            print(f"Error recording donation on blockchain: {e}")
            return {
                'success': False,
                'error': str(e),
                'status': 'failed'
            }
    
    def verify_donation(self, transaction_hash: str) -> Dict:
        """
        Verify a donation transaction on the blockchain
        
        Args:
            transaction_hash: Hash of the transaction to verify
            
        Returns:
            Dict containing verification details
        """
        try:
            if not self.is_connected():
                raise Exception("Not connected to blockchain network")

            # First, try to fetch the transaction receipt as a basic verification step.
            try:
                receipt = self.w3.eth.get_transaction_receipt(transaction_hash)
                # If receipt is found, status==1 typically means success
                status_ok = getattr(receipt, 'status', None)
                gas_used = getattr(receipt, 'gasUsed', None)
                block_number = getattr(receipt, 'blockNumber', None)

                # If receipt exists, return a basic verification payload
                if receipt:
                    return {
                        'success': True,
                        'is_valid': True if status_ok in (1, True) else False,
                        'block_number': block_number,
                        'gas_used': gas_used,
                        'transaction_hash': transaction_hash
                    }
            except Exception as receipt_err:
                # If receipt isn't found or RPC call fails, continue to contract-based verification
                print(f"Info: could not get tx receipt ({transaction_hash}): {receipt_err}")

            # If we have a donation contract and ABI, try to query contract data/events
            if self.donation_contract:
                try:
                    # Since the ABI may not match exact contract layout, attempt to parse event logs
                    # or call getDonation if it exists. We'll try a safe call to getDonation with a derived id.
                    donation_id = int(transaction_hash[:8], 16) if len(transaction_hash) >= 8 else 1
                    donation_data = self.donation_contract.functions.getDonation(donation_id).call()
                    is_valid = donation_data[6] if len(donation_data) > 6 else False
                    return {
                        'success': True,
                        'is_valid': is_valid,
                        'fundraiser_id': donation_data[4] if len(donation_data) > 4 else 0,
                        'donor_address': donation_data[1] if len(donation_data) > 1 else '0x0',
                        'amount': self.w3.from_wei(donation_data[3], 'ether') if len(donation_data) > 3 else 0,
                        'reference_number': donation_data[6] if len(donation_data) > 6 else '',
                        'timestamp': donation_data[7] if len(donation_data) > 7 else 0
                    }
                except Exception as inner_e:
                    print(f"Warning: contract-based verification failed: {inner_e}")

            return {
                'success': False,
                'error': 'Could not verify transaction on-chain; receipt or contract verification failed',
                'transaction_hash': transaction_hash
            }
            
        except Exception as e:
            print(f"Error verifying donation: {e}")
            return {
                'success': False,
                'error': str(e),
                'is_valid': False
            }
    
    def get_fundraiser_donations(self, fundraiser_id: int) -> List[Dict]:
        """
        Get all donations for a specific fundraiser from blockchain
        
        Args:
            fundraiser_id: ID of the fundraiser
            
        Returns:
            List of donation records
        """
        try:
            if not self.is_connected():
                raise Exception("Not connected to blockchain network")
            
            if not self.donation_contract:
                raise Exception("Donation contract not initialized")
            
            donations = self.donation_contract.functions.getFundraiserDonations(fundraiser_id).call()
            
            result = []
            for donation in donations:
                result.append({
                    'transaction_hash': donation[0].hex(),
                    'donor_address': donation[1],
                    'amount': self.w3.from_wei(donation[2], 'ether'),
                    'reference_number': donation[3],
                    'timestamp': donation[4]
                })
            
            return result
            
        except Exception as e:
            print(f"Error getting fundraiser donations: {e}")
            return []

    def create_fundraiser(self, title: str, description: str, goal_amount: float, creator_address: str, end_date: int) -> Dict:
        """
        Create a fundraiser on the blockchain
        
        Args:
            title: Title of the fundraiser
            description: Description of the fundraiser
            goal_amount: Goal amount in ETH
            creator_address: Ethereum address of the creator
            end_date: End date as Unix timestamp
            
        Returns:
            Dict containing fundraiser creation details
        """
        try:
            if not self.is_connected():
                raise Exception("Not connected to blockchain network")
            
            if not self.fundraiser_contract:
                raise Exception("Fundraiser contract not initialized")
            
            creator_address = self.w3.to_checksum_address(creator_address)
            
            goal_amount_wei = self.w3.to_wei(goal_amount, 'ether')
            
            transaction = self.fundraiser_contract.functions.createFundraiser(
                title,
                description,
                goal_amount_wei,
                creator_address,
                end_date
            ).build_transaction({
                'from': self.wallet_address,
                'gas': 300000,
                'gasPrice': self.w3.eth.gas_price,
                'nonce': self.w3.eth.get_transaction_count(self.wallet_address),
            })
            
            signed_txn = self.w3.eth.account.sign_transaction(transaction, self.account.key)
            
            try:
                raw_tx = signed_txn.raw_transaction
            except AttributeError:
                raw_tx = signed_txn.rawTransaction
            
            tx_hash = self.w3.eth.send_raw_transaction(raw_tx)
            tx_receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
            
            return {
                'success': True,
                'transaction_hash': tx_hash.hex(),
                'block_number': tx_receipt.blockNumber,
                'status': 'success'
            }
            
        except Exception as e:
            print(f"Error creating fundraiser on blockchain: {e}")
            return {
                'success': False,
                'error': str(e),
                'status': 'failed'
            }
    
    def generate_transaction_hash(self, data: Dict) -> str:
        """
        Generate a unique transaction hash for internal tracking
        
        Args:
            data: Transaction data dictionary
            
        Returns:
            SHA-256 hash of the transaction data
        """
        data_string = json.dumps(data, sort_keys=True)
        return hashlib.sha256(data_string.encode()).hexdigest()
    
    def get_transaction_status(self, transaction_hash: str) -> Dict:
        """
        Get the status of a blockchain transaction
        
        Args:
            transaction_hash: Hash of the transaction
            
        Returns:
            Dict containing transaction status
        """
        try:
            if not self.is_connected():
                raise Exception("Not connected to blockchain network")
            
            tx_receipt = self.w3.eth.get_transaction_receipt(transaction_hash)
            
            return {
                'success': True,
                'status': 'success' if tx_receipt.status == 1 else 'failed',
                'block_number': tx_receipt.blockNumber,
                'gas_used': tx_receipt.gasUsed,
                'transaction_hash': transaction_hash
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'status': 'unknown'
            }
    
    def get_wallet_transactions(self, wallet_address: str = None, limit: int = 50, start_block: int = None) -> List[Dict]:
        """
        Get all transactions for a wallet address from the blockchain
        
        Args:
            wallet_address: Address to get transactions for (defaults to platform wallet)
            limit: Maximum number of transactions to return
            start_block: Block number to start from (for pagination)
            
        Returns:
            List of transaction records from blockchain
        """
        try:
            if not self.is_connected():
                raise Exception("Not connected to blockchain network")
            
            if not wallet_address:
                wallet_address = self.wallet_address
            
            wallet_address = self.w3.to_checksum_address(wallet_address)
            
            print(f"🔍 Fetching transactions for wallet: {wallet_address}")
            
            current_block = self.w3.eth.block_number
            print(f"📊 Current block: {current_block}")
            
            if not start_block:
                start_block = max(0, current_block - 10000)
            
            print(f"🔍 Scanning from block {start_block} to {current_block}")
            
            transactions = []
            processed_count = 0
            
            for block_num in range(current_block, start_block - 1, -1):
                if processed_count >= limit:
                    break
                
                try:
                    block = self.w3.eth.get_block(block_num, full_transactions=True)
                    
                    if not block or not block.transactions:
                        continue
                    
                    for tx in block.transactions:
                        if processed_count >= limit:
                            break
                        
                        if not tx or 'from' not in tx:
                            continue
                            
                        from_address = tx['from'].lower() if tx['from'] else ''
                        to_address = tx['to'].lower() if tx['to'] else ''
                        
                        if (from_address == wallet_address.lower() or 
                            to_address == wallet_address.lower()):
                            
                            try:
                                receipt = self.w3.eth.get_transaction_receipt(tx.hash)
                                
                                is_contract_tx = False
                                contract_address = None
                                function_name = None
                                
                                contract_addresses = []
                                if self.donation_contract_address:
                                    contract_addresses.append(self.donation_contract_address.lower())
                                if self.fundraiser_contract_address:
                                    contract_addresses.append(self.fundraiser_contract_address.lower())
                                
                                if (tx['to'] and contract_addresses and 
                                    tx['to'].lower() in contract_addresses):
                                    is_contract_tx = True
                                    contract_address = tx['to']
                                    
                                    try:
                                        if tx['to'].lower() == self.donation_contract_address.lower():
                                            decoded = self.donation_contract.decode_function_input(tx['input'])
                                            function_name = decoded[0].fn_name
                                        elif tx['to'].lower() == self.fundraiser_contract_address.lower():
                                            decoded = self.fundraiser_contract.decode_function_input(tx['input'])
                                            function_name = decoded[0].fn_name
                                    except:
                                        function_name = "Unknown"
                                
                                transaction_data = {
                                    'hash': tx.hash.hex(),
                                    'block_number': block_num,
                                    'from_address': tx['from'] or '0x0',
                                    'to_address': tx['to'] or '0x0',
                                    'value': float(self.w3.from_wei(tx['value'], 'ether')),
                                    'gas_used': receipt.gasUsed,
                                    'gas_price': tx['gasPrice'],
                                    'timestamp': block.timestamp,
                                    'status': 'success' if receipt.status == 1 else 'failed',
                                    'is_contract_tx': is_contract_tx,
                                    'contract_address': contract_address,
                                    'function_name': function_name,
                                    'transaction_type': 'Contract Creation' if not tx['to'] else ('Contract Interaction' if is_contract_tx else 'Transfer')
                                }
                                
                                transactions.append(transaction_data)
                                processed_count += 1
                                
                                if processed_count % 10 == 0:
                                    print(f"📈 Found {processed_count} transactions...")
                                    
                            except Exception as e:
                                print(f"⚠️  Error processing transaction {tx.hash.hex()}: {e}")
                                continue
                                
                except Exception as e:
                    print(f"⚠️  Error processing block {block_num}: {e}")
                    continue
            
            print(f"✅ Found {len(transactions)} transactions for wallet {wallet_address}")
            return transactions
            
        except Exception as e:
            print(f"❌ Error fetching wallet transactions: {e}")
            return []


# ------------------ Encryption helpers ------------------
def _derive_key_from_env() -> bytes:
    """Derive a 32-byte AES key from ENCRYPTION_KEY or PRIVATE_KEY using SHA-256/HKDF."""
    # Prefer explicit ENCRYPTION_KEY (base64 or raw); fall back to PRIVATE_KEY
    raw = os.getenv('ENCRYPTION_KEY') or os.getenv('PRIVATE_KEY') or ''
    if raw.startswith('0x'):
        raw = raw[2:]
    raw_bytes = raw.encode('utf-8')

    # Use HKDF to derive a fixed-length key
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b'ReliePH-encryption-salt',
        info=b'ReliePH-aes-key',
    )
    return hkdf.derive(raw_bytes)

def encrypt_payload(plaintext: bytes) -> Dict:
    """Encrypt bytes using AES-256-GCM. Returns dict with base64 ciphertext, iv, tag."""
    key = _derive_key_from_env()
    aesgcm = AESGCM(key)
    iv = os.urandom(12)
    ct = aesgcm.encrypt(iv, plaintext, None)
    ciphertext = ct[:-16]
    tag = ct[-16:]
    return {
        'ciphertext': base64.b64encode(ciphertext).decode('utf-8'),
        'iv': base64.b64encode(iv).decode('utf-8'),
        'tag': base64.b64encode(tag).decode('utf-8')
    }


def decrypt_payload(enc_obj: Dict) -> Optional[bytes]:
    """Decrypt dict produced by encrypt_payload. Returns plaintext bytes or None on failure."""
    try:
        key = _derive_key_from_env()
        aesgcm = AESGCM(key)
        iv = base64.b64decode(enc_obj['iv'])
        ciphertext = base64.b64decode(enc_obj['ciphertext'])
        tag = base64.b64decode(enc_obj['tag'])
        ct_and_tag = ciphertext + tag
        pt = aesgcm.decrypt(iv, ct_and_tag, None)
        return pt
    except Exception as e:
        print(f"Error decrypting payload: {e}")
        return None


def sha256_hex(data: bytes) -> str:
    digest = hashes.Hash(hashes.SHA256())
    digest.update(data)
    return digest.finalize().hex()

    
blockchain_manager = None

def get_blockchain_manager() -> BlockchainManager:
    """Get the global blockchain manager instance"""
    global blockchain_manager
    if blockchain_manager is None:
        rpc_url = os.getenv('INFURA_URL')
        private_key = os.getenv('PRIVATE_KEY')
        donation_contract_address = os.getenv('DONATION_CONTRACT_ADDRESS')
        fundraiser_contract_address = os.getenv('FUNDRAISER_CONTRACT_ADDRESS')
        
        blockchain_manager = BlockchainManager(
            rpc_url=rpc_url,
            private_key=private_key,
            donation_contract_address=donation_contract_address,
            fundraiser_contract_address=fundraiser_contract_address
        )
    return blockchain_manager

def init_blockchain_contracts(donation_contract_address: str, fundraiser_contract_address: str):
    """Initialize contract addresses"""
    global blockchain_manager
    if blockchain_manager:
        # Convert addresses to checksum format
        if donation_contract_address:
            try:
                donation_contract_address = blockchain_manager.w3.to_checksum_address(donation_contract_address)
            except Exception as e:
                print(f"Warning: Invalid donation contract address: {e}")
                donation_contract_address = None
        
        if fundraiser_contract_address:
            try:
                fundraiser_contract_address = blockchain_manager.w3.to_checksum_address(fundraiser_contract_address)
            except Exception as e:
                print(f"Warning: Invalid fundraiser contract address: {e}")
                fundraiser_contract_address = None
        
        blockchain_manager.donation_contract_address = donation_contract_address
        blockchain_manager.fundraiser_contract_address = fundraiser_contract_address
        
        # Reinitialize contract instances
        if blockchain_manager.donation_contract_abi and donation_contract_address:
            blockchain_manager.donation_contract = blockchain_manager.w3.eth.contract(
                address=donation_contract_address,
                abi=blockchain_manager.donation_contract_abi
            )
        
        if blockchain_manager.fundraiser_contract_abi and fundraiser_contract_address:
            blockchain_manager.fundraiser_contract = blockchain_manager.w3.eth.contract(
                address=fundraiser_contract_address,
                abi=blockchain_manager.fundraiser_contract_abi
            )

# Convenience functions for easy integration
def record_donation_on_blockchain(fundraiser_id: int, donor_address: str, amount: float, reference_number: str) -> Dict:
    """Record a donation on the blockchain"""
    manager = get_blockchain_manager()
    return manager.record_donation(fundraiser_id, donor_address, amount, reference_number)

def verify_donation_on_blockchain(transaction_hash: str) -> Dict:
    """Verify a donation on the blockchain"""
    manager = get_blockchain_manager()
    return manager.verify_donation(transaction_hash)

def get_fundraiser_donations_from_blockchain(fundraiser_id: int) -> List[Dict]:
    """Get fundraiser donations from blockchain"""
    manager = get_blockchain_manager()
    return manager.get_fundraiser_donations(fundraiser_id)

def create_fundraiser_on_blockchain(title: str, description: str, goal_amount: float, creator_address: str, end_date: int) -> Dict:
    """Create a fundraiser on the blockchain"""
    manager = get_blockchain_manager()
    return manager.create_fundraiser(title, description, goal_amount, creator_address, end_date)

def check_blockchain_connection() -> bool:
    """Check if blockchain connection is working"""
    manager = get_blockchain_manager()
    return manager.is_connected()

def get_wallet_address() -> str:
    """Get the wallet address being used for transactions"""
    manager = get_blockchain_manager()
    return manager.wallet_address

def get_wallet_balance() -> float:
    """Get the wallet balance in ETH"""
    manager = get_blockchain_manager()
    return manager.get_balance()

def to_checksum_address(address: str) -> str:
    """Convert an address to checksum format safely"""
    try:
        manager = get_blockchain_manager()
        return manager.w3.to_checksum_address(address)
    except Exception as e:
        print(f"Error converting address to checksum: {e}")
        return address

def get_wallet_transactions_from_blockchain(wallet_address: str = None, limit: int = 50, start_block: int = None) -> List[Dict]:
    """Get wallet transactions from blockchain"""
    manager = get_blockchain_manager()
    return manager.get_wallet_transactions(wallet_address, limit, start_block)