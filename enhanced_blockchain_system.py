"""
Enhanced Blockchain Integration for ReliePH
Comprehensive tamper-proof system implementation
"""

from merkle_verification import MerkleTree, BlockchainAnchoring, generate_cryptographic_proof, verify_cryptographic_proof
from multisig_manager import MultiSigManager
from blockchain_anchoring import DatabaseAnchoring, TimestampVerification
from audit_trail_enhanced import AuditTrailManager, AuditEventType, DocumentIntegrity
from ipfs_integration import IPFSManager, DocumentStorageManager, EvidenceStorage

class EnhancedBlockchainSystem:
    """Enhanced blockchain system with comprehensive tamper-proof features"""
    
    def __init__(self, blockchain_manager, db_connection_func, private_key: str = None):
        self.blockchain_manager = blockchain_manager
        self.get_db_connection = db_connection_func
        
        # Initialize components
        self.merkle_system = BlockchainAnchoring(blockchain_manager)
        self.multisig_manager = MultiSigManager(db_connection_func)
        self.database_anchoring = DatabaseAnchoring(blockchain_manager, db_connection_func)
        self.timestamp_verification = TimestampVerification(blockchain_manager)
        self.audit_trail = AuditTrailManager(db_connection_func, private_key)
        self.document_integrity = DocumentIntegrity(db_connection_func)
        
        # Initialize IPFS (optional)
        self.ipfs_manager = IPFSManager()
        self.document_storage = DocumentStorageManager(db_connection_func, self.ipfs_manager)
        self.evidence_storage = EvidenceStorage(self.document_storage)
    
    def create_comprehensive_proof(self, transaction_data: Dict, user_id: int) -> Dict:
        """Create comprehensive tamper-proof proof for a transaction"""
        try:
            # 1. Create Merkle tree for batch verification
            merkle_tree = MerkleTree([transaction_data])
            
            # 2. Generate cryptographic proof
            crypto_proof = generate_cryptographic_proof(transaction_data, "your_private_key")
            
            # 3. Create timestamp proof
            timestamp_proof = self.timestamp_verification.create_timestamp_proof(
                json.dumps(transaction_data), "Transaction proof"
            )
            
            # 4. Log audit event
            audit_result = self.audit_trail.log_event(
                AuditEventType.DONATION_CREATED,
                user_id,
                transaction_data,
                "Comprehensive proof creation"
            )
            
            # 5. Store document integrity proof
            doc_content = json.dumps(transaction_data, indent=2)
            doc_proof = self.document_integrity.create_document_proof(
                doc_content, "transaction_proof", user_id
            )
            
            return {
                'success': True,
                'merkle_root': merkle_tree.root,
                'cryptographic_proof': crypto_proof,
                'timestamp_proof': timestamp_proof,
                'audit_chain_hash': audit_result.get('chain_hash'),
                'document_proof': doc_proof,
                'comprehensive_proof_id': hashlib.sha256(
                    f"{merkle_tree.root}:{crypto_proof.get('signature', '')}:{timestamp_proof.get('proof_hash', '')}".encode()
                ).hexdigest(),
                'created_at': datetime.now().isoformat()
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def verify_comprehensive_proof(self, proof_data: Dict) -> Dict:
        """Verify comprehensive tamper-proof proof"""
        try:
            verification_results = {}
            
            # 1. Verify Merkle proof
            if 'merkle_proof' in proof_data:
                merkle_valid = MerkleTree([proof_data['transaction_data']]).verify_proof(
                    proof_data['transaction_data'],
                    proof_data['merkle_proof'],
                    proof_data['merkle_root']
                )
                verification_results['merkle_valid'] = merkle_valid
            
            # 2. Verify cryptographic proof
            if 'cryptographic_proof' in proof_data:
                crypto_valid = verify_cryptographic_proof(
                    proof_data['transaction_data'],
                    proof_data['cryptographic_proof']['signature'],
                    proof_data['cryptographic_proof']['public_key']
                )
                verification_results['cryptographic_valid'] = crypto_valid['is_valid']
            
            # 3. Verify timestamp proof
            if 'timestamp_proof' in proof_data:
                timestamp_valid = self.timestamp_verification.verify_timestamp_proof(
                    proof_data['timestamp_proof']
                )
                verification_results['timestamp_valid'] = timestamp_valid['is_valid']
            
            # 4. Verify audit chain
            if 'audit_chain_hash' in proof_data:
                audit_valid = self.audit_trail.verify_audit_chain()
                verification_results['audit_valid'] = audit_valid['chain_integrity']
            
            # 5. Verify document integrity
            if 'document_proof' in proof_data:
                doc_content = json.dumps(proof_data['transaction_data'], indent=2)
                doc_valid = self.document_integrity.verify_document_integrity(
                    doc_content, proof_data['document_proof']['proof_id']
                )
                verification_results['document_valid'] = doc_valid['is_valid']
            
            # Overall verification
            all_valid = all(verification_results.values())
            
            return {
                'success': True,
                'overall_valid': all_valid,
                'verification_results': verification_results,
                'verification_timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def create_database_anchor_batch(self, table_name: str, record_ids: List[int] = None) -> Dict:
        """Create blockchain anchor for database records"""
        return self.database_anchoring.create_database_anchor(table_name, record_ids)
    
    def verify_record_integrity(self, table_name: str, record_id: int) -> Dict:
        """Verify record integrity against blockchain anchor"""
        return self.database_anchoring.verify_record_integrity(table_name, record_id)
    
    def create_multisig_request(self, operation_type: str, operation_data: Dict, 
                               requester_id: int, description: str = "") -> Dict:
        """Create multi-signature request for critical operations"""
        return self.multisig_manager.create_multisig_request(
            operation_type, operation_data, requester_id, description
        )
    
    def approve_multisig_request(self, request_id: str, approver_id: int, 
                                signature: str, approval_note: str = "") -> Dict:
        """Approve multi-signature request"""
        return self.multisig_manager.approve_request(request_id, approver_id, signature, approval_note)
    
    def store_evidence_document(self, fund_id: int, document_content: str, 
                               document_type: str, user_id: int) -> Dict:
        """Store evidence document with IPFS"""
        return self.document_storage.store_fundraiser_document(
            fund_id, document_content, document_type, user_id
        )
    
    def get_audit_report(self, user_id: int = None, event_type: str = None, 
                        start_date: datetime = None, end_date: datetime = None) -> Dict:
        """Get comprehensive audit report"""
        return self.audit_trail.get_audit_report(user_id, event_type, start_date, end_date)
    
    def create_all_schemas(self):
        """Create all database schemas for enhanced blockchain system"""
        schemas = []
        
        # Add all schema creation methods
        schemas.append(self.multisig_manager.create_multisig_schema())
        schemas.append(self.database_anchoring.create_anchor_schema())
        schemas.append(self.audit_trail.create_audit_schema())
        schemas.append(self.document_integrity.create_document_schema())
        schemas.append(self.document_storage.create_ipfs_schema())
        
        return "\n\n".join(schemas)


def integrate_enhanced_blockchain(app_instance, blockchain_manager, get_db_connection):
    """Integrate enhanced blockchain system into Flask app"""
    
    # Initialize enhanced system
    enhanced_system = EnhancedBlockchainSystem(blockchain_manager, get_db_connection)
    
    # Add routes for enhanced functionality
    @app_instance.route('/api/blockchain/comprehensive-proof', methods=['POST'])
    def create_comprehensive_proof():
        """Create comprehensive tamper-proof proof"""
        data = request.get_json()
        user_id = session.get('user_id', 0)
        
        result = enhanced_system.create_comprehensive_proof(data, user_id)
        return jsonify(result)
    
    @app_instance.route('/api/blockchain/verify-comprehensive-proof', methods=['POST'])
    def verify_comprehensive_proof():
        """Verify comprehensive tamper-proof proof"""
        data = request.get_json()
        
        result = enhanced_system.verify_comprehensive_proof(data)
        return jsonify(result)
    
    @app_instance.route('/api/blockchain/create-anchor', methods=['POST'])
    def create_database_anchor():
        """Create blockchain anchor for database records"""
        data = request.get_json()
        table_name = data.get('table_name')
        record_ids = data.get('record_ids')
        
        result = enhanced_system.create_database_anchor_batch(table_name, record_ids)
        return jsonify(result)
    
    @app_instance.route('/api/blockchain/verify-record/<table_name>/<int:record_id>')
    def verify_record_integrity(table_name, record_id):
        """Verify record integrity"""
        result = enhanced_system.verify_record_integrity(table_name, record_id)
        return jsonify(result)
    
    @app_instance.route('/api/blockchain/multisig/create', methods=['POST'])
    def create_multisig_request():
        """Create multi-signature request"""
        data = request.get_json()
        user_id = session.get('user_id', 0)
        
        result = enhanced_system.create_multisig_request(
            data.get('operation_type'),
            data.get('operation_data'),
            user_id,
            data.get('description', '')
        )
        return jsonify(result)
    
    @app_instance.route('/api/blockchain/multisig/approve', methods=['POST'])
    def approve_multisig_request():
        """Approve multi-signature request"""
        data = request.get_json()
        user_id = session.get('user_id', 0)
        
        result = enhanced_system.approve_multisig_request(
            data.get('request_id'),
            user_id,
            data.get('signature'),
            data.get('approval_note', '')
        )
        return jsonify(result)
    
    @app_instance.route('/api/blockchain/audit/report')
    def get_audit_report():
        """Get audit report"""
        user_id = request.args.get('user_id', type=int)
        event_type = request.args.get('event_type')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        result = enhanced_system.get_audit_report(user_id, event_type, start_date, end_date)
        return jsonify(result)
    
    @app_instance.route('/api/blockchain/evidence/store', methods=['POST'])
    def store_evidence():
        """Store evidence document"""
        data = request.get_json()
        user_id = session.get('user_id', 0)
        
        result = enhanced_system.store_evidence_document(
            data.get('fund_id'),
            data.get('document_content'),
            data.get('document_type'),
            user_id
        )
        return jsonify(result)
    
    return enhanced_system
