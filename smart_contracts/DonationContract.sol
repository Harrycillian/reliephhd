// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/**
 * @title DonationContract
 * @dev Smart contract for recording and verifying donations on ReliePH platform
 * @author ReliePH Team
 */
contract DonationContract {
    
    // Struct to store donation information
    struct Donation {
        bytes32 transactionHash;
        address donor;
        uint256 amount;
        string referenceNumber;
        uint256 timestamp;
        bool isValid;
    }
    
    // Mapping to store donations by fundraiser ID
    mapping(uint256 => Donation[]) public fundraiserDonations;
    
    // Mapping to store donation by transaction hash for verification
    mapping(bytes32 => Donation) public donationsByHash;
    
    // Mapping to track total donations per fundraiser
    mapping(uint256 => uint256) public totalDonations;
    
    // Events
    event DonationRecorded(
        bytes32 indexed transactionHash,
        uint256 indexed fundraiserId,
        address indexed donor,
        uint256 amount,
        string referenceNumber
    );
    
    event DonationVerified(
        bytes32 indexed transactionHash,
        bool isValid
    );
    
    // Modifiers
    modifier onlyValidAddress(address _address) {
        require(_address != address(0), "Invalid address");
        _;
    }
    
    modifier onlyValidAmount(uint256 _amount) {
        require(_amount > 0, "Amount must be greater than 0");
        _;
    }
    
    /**
     * @dev Record a new donation
     * @param fundraiserId ID of the fundraiser
     * @param donor Address of the donor
     * @param amount Donation amount in wei
     * @param referenceNumber Reference number from the platform
     * @return transactionHash Unique hash for this donation
     */
    function recordDonation(
        uint256 fundraiserId,
        address donor,
        uint256 amount,
        string memory referenceNumber
    ) 
        external 
        onlyValidAddress(donor)
        onlyValidAmount(amount)
        returns (bytes32 transactionHash)
    {
        // Generate unique transaction hash
        transactionHash = keccak256(
            abi.encodePacked(
                fundraiserId,
                donor,
                amount,
                referenceNumber,
                block.timestamp,
                block.number
            )
        );
        
        // Create donation record
        Donation memory newDonation = Donation({
            transactionHash: transactionHash,
            donor: donor,
            amount: amount,
            referenceNumber: referenceNumber,
            timestamp: block.timestamp,
            isValid: true
        });
        
        // Store donation
        fundraiserDonations[fundraiserId].push(newDonation);
        donationsByHash[transactionHash] = newDonation;
        
        // Update total donations
        totalDonations[fundraiserId] += amount;
        
        // Emit event
        emit DonationRecorded(
            transactionHash,
            fundraiserId,
            donor,
            amount,
            referenceNumber
        );
        
        return transactionHash;
    }
    
    /**
     * @dev Verify a donation by transaction hash
     * @param transactionHash Hash of the transaction to verify
     * @return isValid Whether the donation is valid
     * @return fundraiserId ID of the fundraiser
     * @return donor Address of the donor
     * @return amount Donation amount
     * @return referenceNumber Reference number
     * @return timestamp When the donation was made
     */
    function verifyDonation(bytes32 transactionHash)
        external
        view
        returns (
            bool isValid,
            uint256 fundraiserId,
            address donor,
            uint256 amount,
            string memory referenceNumber,
            uint256 timestamp
        )
    {
        Donation memory donation = donationsByHash[transactionHash];
        
        return (
            donation.isValid,
            _findFundraiserId(transactionHash),
            donation.donor,
            donation.amount,
            donation.referenceNumber,
            donation.timestamp
        );
    }
    
    /**
     * @dev Get all donations for a specific fundraiser
     * @param fundraiserId ID of the fundraiser
     * @return donations Array of donation records
     */
    function getFundraiserDonations(uint256 fundraiserId)
        external
        view
        returns (Donation[] memory donations)
    {
        return fundraiserDonations[fundraiserId];
    }
    
    /**
     * @dev Get total amount donated to a fundraiser
     * @param fundraiserId ID of the fundraiser
     * @return total Total amount donated
     */
    function getTotalDonations(uint256 fundraiserId)
        external
        view
        returns (uint256 total)
    {
        return totalDonations[fundraiserId];
    }
    
    /**
     * @dev Get donation count for a fundraiser
     * @param fundraiserId ID of the fundraiser
     * @return count Number of donations
     */
    function getDonationCount(uint256 fundraiserId)
        external
        view
        returns (uint256 count)
    {
        return fundraiserDonations[fundraiserId].length;
    }
    
    /**
     * @dev Get donation by index for a fundraiser
     * @param fundraiserId ID of the fundraiser
     * @param index Index of the donation
     * @return donation Donation record
     */
    function getDonationByIndex(uint256 fundraiserId, uint256 index)
        external
        view
        returns (Donation memory donation)
    {
        require(index < fundraiserDonations[fundraiserId].length, "Index out of bounds");
        return fundraiserDonations[fundraiserId][index];
    }
    
    /**
     * @dev Invalidate a donation (for fraud prevention)
     * @param transactionHash Hash of the transaction to invalidate
     * @param fundraiserId ID of the fundraiser
     */
    function invalidateDonation(bytes32 transactionHash, uint256 fundraiserId)
        external
    {
        require(donationsByHash[transactionHash].isValid, "Donation already invalid");
        
        // Mark as invalid
        donationsByHash[transactionHash].isValid = false;
        
        // Update total donations
        totalDonations[fundraiserId] -= donationsByHash[transactionHash].amount;
        
        emit DonationVerified(transactionHash, false);
    }
    
    /**
     * @dev Internal function to find fundraiser ID by transaction hash
     * @param transactionHash Hash to search for
     * @return fundraiserId ID of the fundraiser
     */
    function _findFundraiserId(bytes32 transactionHash)
        internal
        view
        returns (uint256 fundraiserId)
    {
        // This is a simplified implementation
        // In a production environment, you might want to store this mapping
        // For now, we'll return 0 as a placeholder
        return 0;
    }
    
    /**
     * @dev Get contract statistics
     * @return totalFundraisers Total number of fundraisers with donations
     * @return totalDonationsAll Total donations across all fundraisers
     */
    function getContractStats()
        external
        view
        returns (uint256 totalFundraisers, uint256 totalDonationsAll)
    {
        // This would require additional storage to track efficiently
        // For now, return placeholder values
        return (0, 0);
    }
}
