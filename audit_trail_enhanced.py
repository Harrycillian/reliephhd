"""
Enhanced audit trail system with cryptographic proofs
Provides immutable audit logs with cryptographic verification
"""

import json
import hashlib
import hmac
from typing import List, Dict, Optional, Any
from datetime import datetime
from enum import Enum

class AuditEventType(Enum):
    DONATION_CREATED = "donation_created"
    DONATION_VERIFIED = "donation_verified"
    FUNDRAISER_CREATED = "fundraiser_created"
    FUNDRAISER_APPROVED = "fundraiser_approved"
    USER_LOGIN = "user_login"
    ADMIN_ACTION = "admin_action"
    BLOCKCHAIN_TRANSACTION = "blockchain_transaction"
    SYSTEM_EVENT = "system_event"

class AuditTrailManager:
    """Enhanced audit trail manager with cryptographic proofs"""
    
    def __init__(self, db_connection_func, private_key: str = None):
        self.get_db_connection = db_connection_func
        self.private_key = private_key or self._generate_default_key()
        self.chain_hash = None  # For chaining audit entries
    
    def log_event(self, event_type: AuditEventType, user_id: int, 
                  event_data: Dict, description: str = "") -> Dict:
        """Log an audit event with cryptographic proof"""
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            
            # Create event entry
            event_entry = {
                'event_type': event_type.value,
                'user_id': user_id,
                'event_data': event_data,
                'description': description,
                'timestamp': datetime.now().isoformat(),
                'previous_hash': self.chain_hash
            }
            
            # Generate cryptographic proof
            proof = self._generate_cryptographic_proof(event_entry)
            
            # Calculate chain hash for next entry
            chain_data = json.dumps(event_entry, sort_keys=True) + proof['signature']
            self.chain_hash = hashlib.sha256(chain_data.encode()).hexdigest()
            
            # Store in database
            cursor.execute("""
                INSERT INTO audit_trail (
                    event_type, user_id, event_data, description,
                    cryptographic_proof, chain_hash, previous_hash,
                    created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                event_type.value, user_id, json.dumps(event_data),
                description, json.dumps(proof), self.chain_hash,
                event_entry['previous_hash'], datetime.now()
            ))
            
            audit_id = cursor.lastrowid
            conn.commit()
            cursor.close()
            conn.close()
            
            return {
                'success': True,
                'audit_id': audit_id,
                'chain_hash': self.chain_hash,
                'proof': proof,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def verify_audit_chain(self, start_id: int = None, end_id: int = None) -> Dict:
        """Verify the integrity of the audit chain"""
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            
            # Get audit entries
            if start_id and end_id:
                cursor.execute("""
                    SELECT * FROM audit_trail 
                    WHERE id BETWEEN %s AND %s 
                    ORDER BY id ASC
                """, (start_id, end_id))
            else:
                cursor.execute("""
                    SELECT * FROM audit_trail 
                    ORDER BY id ASC
                """)
            
            entries = cursor.fetchall()
            column_names = [desc[0] for desc in cursor.description]
            
            verification_results = []
            previous_hash = None
            
            for entry in entries:
                entry_dict = dict(zip(column_names, entry))
                
                # Verify cryptographic proof
                proof = json.loads(entry_dict['cryptographic_proof'])
                event_data = {
                    'event_type': entry_dict['event_type'],
                    'user_id': entry_dict['user_id'],
                    'event_data': json.loads(entry_dict['event_data']),
                    'description': entry_dict['description'],
                    'timestamp': entry_dict['created_at'].isoformat(),
                    'previous_hash': entry_dict['previous_hash']
                }
                
                proof_valid = self._verify_cryptographic_proof(event_data, proof)
                
                # Verify chain integrity
                chain_valid = True
                if previous_hash is not None:
                    chain_valid = (entry_dict['previous_hash'] == previous_hash)
                
                verification_results.append({
                    'audit_id': entry_dict['id'],
                    'event_type': entry_dict['event_type'],
                    'timestamp': entry_dict['created_at'].isoformat(),
                    'proof_valid': proof_valid,
                    'chain_valid': chain_valid,
                    'overall_valid': proof_valid and chain_valid
                })
                
                previous_hash = entry_dict['chain_hash']
            
            cursor.close()
            conn.close()
            
            # Check overall chain integrity
            all_valid = all(result['overall_valid'] for result in verification_results)
            
            return {
                'success': True,
                'chain_integrity': all_valid,
                'total_entries': len(verification_results),
                'verification_results': verification_results,
                'verification_timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def get_audit_report(self, user_id: int = None, event_type: str = None, 
                        start_date: datetime = None, end_date: datetime = None) -> Dict:
        """Generate comprehensive audit report"""
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            
            # Build query
            query = "SELECT * FROM audit_trail WHERE 1=1"
            params = []
            
            if user_id:
                query += " AND user_id = %s"
                params.append(user_id)
            
            if event_type:
                query += " AND event_type = %s"
                params.append(event_type)
            
            if start_date:
                query += " AND created_at >= %s"
                params.append(start_date)
            
            if end_date:
                query += " AND created_at <= %s"
                params.append(end_date)
            
            query += " ORDER BY created_at DESC"
            
            cursor.execute(query, params)
            entries = cursor.fetchall()
            column_names = [desc[0] for desc in cursor.description]
            
            # Process entries
            audit_entries = []
            for entry in entries:
                entry_dict = dict(zip(column_names, entry))
                
                # Add user information
                cursor.execute("SELECT name, email FROM users WHERE id = %s", 
                             (entry_dict['user_id'],))
                user_info = cursor.fetchone()
                
                audit_entry = {
                    'audit_id': entry_dict['id'],
                    'event_type': entry_dict['event_type'],
                    'user_id': entry_dict['user_id'],
                    'user_name': user_info[0] if user_info else 'Unknown',
                    'user_email': user_info[1] if user_info else 'Unknown',
                    'description': entry_dict['description'],
                    'event_data': json.loads(entry_dict['event_data']),
                    'timestamp': entry_dict['created_at'].isoformat(),
                    'chain_hash': entry_dict['chain_hash'],
                    'previous_hash': entry_dict['previous_hash']
                }
                
                audit_entries.append(audit_entry)
            
            # Generate summary statistics
            cursor.execute("""
                SELECT event_type, COUNT(*) as count 
                FROM audit_trail 
                WHERE created_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)
                GROUP BY event_type
            """)
            
            event_stats = {}
            for row in cursor.fetchall():
                event_stats[row[0]] = row[1]
            
            cursor.close()
            conn.close()
            
            return {
                'success': True,
                'audit_entries': audit_entries,
                'total_entries': len(audit_entries),
                'event_statistics': event_stats,
                'report_generated_at': datetime.now().isoformat(),
                'filters': {
                    'user_id': user_id,
                    'event_type': event_type,
                    'start_date': start_date.isoformat() if start_date else None,
                    'end_date': end_date.isoformat() if end_date else None
                }
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _generate_cryptographic_proof(self, event_data: Dict) -> Dict:
        """Generate cryptographic proof for audit event"""
        try:
            # Create data hash
            data_str = json.dumps(event_data, sort_keys=True, separators=(',', ':'))
            data_hash = hashlib.sha256(data_str.encode()).hexdigest()
            
            # Generate HMAC signature
            signature = hmac.new(
                self.private_key.encode(),
                data_hash.encode(),
                hashlib.sha256
            ).hexdigest()
            
            # Generate proof hash
            proof_data = {
                'data_hash': data_hash,
                'signature': signature,
                'timestamp': datetime.now().isoformat(),
                'algorithm': 'HMAC-SHA256'
            }
            
            proof_hash = hashlib.sha256(
                json.dumps(proof_data, sort_keys=True).encode()
            ).hexdigest()
            
            return {
                'proof_hash': proof_hash,
                'data_hash': data_hash,
                'signature': signature,
                'timestamp': datetime.now().isoformat(),
                'algorithm': 'HMAC-SHA256'
            }
            
        except Exception as e:
            return {'error': str(e)}
    
    def _verify_cryptographic_proof(self, event_data: Dict, proof: Dict) -> bool:
        """Verify cryptographic proof for audit event"""
        try:
            # Recreate data hash
            data_str = json.dumps(event_data, sort_keys=True, separators=(',', ':'))
            expected_data_hash = hashlib.sha256(data_str.encode()).hexdigest()
            
            # Verify data hash
            if expected_data_hash != proof['data_hash']:
                return False
            
            # Verify HMAC signature
            expected_signature = hmac.new(
                self.private_key.encode(),
                expected_data_hash.encode(),
                hashlib.sha256
            ).hexdigest()
            
            return expected_signature == proof['signature']
            
        except Exception as e:
            return False
    
    def _generate_default_key(self) -> str:
        """Generate default private key for HMAC"""
        return hashlib.sha256("ReliePH-Audit-Trail-Key".encode()).hexdigest()
    
    def create_audit_schema(self):
        """Create database schema for audit trail"""
        return """
        -- Enhanced audit trail table
        CREATE TABLE IF NOT EXISTS audit_trail (
            id INT(11) NOT NULL PRIMARY KEY AUTO_INCREMENT,
            event_type VARCHAR(50) NOT NULL,
            user_id INT(11) NOT NULL,
            event_data JSON NOT NULL,
            description TEXT,
            cryptographic_proof JSON NOT NULL,
            chain_hash VARCHAR(64) NOT NULL,
            previous_hash VARCHAR(64),
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            INDEX idx_event_type (event_type),
            INDEX idx_user_id (user_id),
            INDEX idx_created_at (created_at),
            INDEX idx_chain_hash (chain_hash)
        );
        """


class DocumentIntegrity:
    """Document integrity verification system"""
    
    def __init__(self, db_connection_func):
        self.get_db_connection = db_connection_func
    
    def create_document_proof(self, document_content: str, document_type: str, 
                             user_id: int) -> Dict:
        """Create integrity proof for a document"""
        try:
            # Generate document hash
            doc_hash = hashlib.sha256(document_content.encode()).hexdigest()
            
            # Create proof data
            proof_data = {
                'document_hash': doc_hash,
                'document_type': document_type,
                'user_id': user_id,
                'timestamp': datetime.now().isoformat(),
                'content_length': len(document_content)
            }
            
            # Generate proof hash
            proof_hash = hashlib.sha256(
                json.dumps(proof_data, sort_keys=True).encode()
            ).hexdigest()
            
            # Store in database
            conn = self.get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO document_integrity (
                    document_hash, document_type, user_id, proof_data,
                    proof_hash, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                doc_hash, document_type, user_id, json.dumps(proof_data),
                proof_hash, datetime.now()
            ))
            
            proof_id = cursor.lastrowid
            conn.commit()
            cursor.close()
            conn.close()
            
            return {
                'success': True,
                'proof_id': proof_id,
                'document_hash': doc_hash,
                'proof_hash': proof_hash,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def verify_document_integrity(self, document_content: str, proof_id: int) -> Dict:
        """Verify document integrity against stored proof"""
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            
            # Get stored proof
            cursor.execute("""
                SELECT * FROM document_integrity WHERE id = %s
            """, (proof_id,))
            
            result = cursor.fetchone()
            if not result:
                return {'success': False, 'error': 'Proof not found'}
            
            # Calculate current document hash
            current_hash = hashlib.sha256(document_content.encode()).hexdigest()
            
            # Compare with stored hash
            stored_hash = result[1]  # document_hash column
            
            is_valid = current_hash == stored_hash
            
            cursor.close()
            conn.close()
            
            return {
                'success': True,
                'is_valid': is_valid,
                'current_hash': current_hash,
                'stored_hash': stored_hash,
                'verification_timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def create_document_schema(self):
        """Create database schema for document integrity"""
        return """
        -- Document integrity table
        CREATE TABLE IF NOT EXISTS document_integrity (
            id INT(11) NOT NULL PRIMARY KEY AUTO_INCREMENT,
            document_hash VARCHAR(64) NOT NULL,
            document_type VARCHAR(50) NOT NULL,
            user_id INT(11) NOT NULL,
            proof_data JSON NOT NULL,
            proof_hash VARCHAR(64) NOT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            INDEX idx_document_hash (document_hash),
            INDEX idx_document_type (document_type),
            INDEX idx_user_id (user_id),
            INDEX idx_created_at (created_at)
        );
        """
