// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/**
 * @title FundraiserContract
 * @dev Smart contract for managing fundraisers on ReliePH platform
 * @author ReliePH Team
 */
contract FundraiserContract {
    
    // Struct to store fundraiser information
    struct Fundraiser {
        string title;
        string description;
        uint256 goalAmount;
        uint256 currentAmount;
        address creator;
        uint256 startDate;
        uint256 endDate;
        bool isActive;
        bool isCompleted;
        uint256 donationCount;
    }
    
    // Mapping to store fundraisers by ID
    mapping(uint256 => Fundraiser) public fundraisers;
    
    // Mapping to track fundraiser IDs by creator
    mapping(address => uint256[]) public creatorFundraisers;
    
    // Counter for fundraiser IDs
    uint256 public fundraiserCounter = 0;
    
    // Events
    event FundraiserCreated(
        uint256 indexed fundraiserId,
        address indexed creator,
        string title,
        uint256 goalAmount,
        uint256 endDate
    );
    
    event FundraiserUpdated(
        uint256 indexed fundraiserId,
        string title,
        string description
    );
    
    event FundraiserCompleted(
        uint256 indexed fundraiserId,
        uint256 finalAmount,
        uint256 donationCount
    );
    
    event FundraiserDeactivated(
        uint256 indexed fundraiserId,
        address indexed creator
    );
    
    // Modifiers
    modifier onlyCreator(uint256 fundraiserId) {
        require(
            fundraisers[fundraiserId].creator == msg.sender,
            "Only the creator can perform this action"
        );
        _;
    }
    
    modifier onlyActiveFundraiser(uint256 fundraiserId) {
        require(
            fundraisers[fundraiserId].isActive,
            "Fundraiser is not active"
        );
        _;
    }
    
    modifier onlyValidFundraiser(uint256 fundraiserId) {
        require(
            fundraiserId > 0 && fundraiserId <= fundraiserCounter,
            "Invalid fundraiser ID"
        );
        _;
    }
    
    /**
     * @dev Create a new fundraiser
     * @param title Title of the fundraiser
     * @param description Description of the fundraiser
     * @param goalAmount Goal amount in wei
     * @param creator Address of the creator
     * @param endDate End date as Unix timestamp
     * @return fundraiserId ID of the created fundraiser
     */
    function createFundraiser(
        string memory title,
        string memory description,
        uint256 goalAmount,
        address creator,
        uint256 endDate
    )
        external
        returns (uint256 fundraiserId)
    {
        require(bytes(title).length > 0, "Title cannot be empty");
        require(bytes(description).length > 0, "Description cannot be empty");
        require(goalAmount > 0, "Goal amount must be greater than 0");
        require(creator != address(0), "Invalid creator address");
        require(endDate > block.timestamp, "End date must be in the future");
        
        // Increment counter and get new ID
        fundraiserCounter++;
        fundraiserId = fundraiserCounter;
        
        // Create fundraiser
        fundraisers[fundraiserId] = Fundraiser({
            title: title,
            description: description,
            goalAmount: goalAmount,
            currentAmount: 0,
            creator: creator,
            startDate: block.timestamp,
            endDate: endDate,
            isActive: true,
            isCompleted: false,
            donationCount: 0
        });
        
        // Add to creator's fundraisers
        creatorFundraisers[creator].push(fundraiserId);
        
        // Emit event
        emit FundraiserCreated(
            fundraiserId,
            creator,
            title,
            goalAmount,
            endDate
        );
        
        return fundraiserId;
    }
    
    /**
     * @dev Get fundraiser details
     * @param fundraiserId ID of the fundraiser
     * @return fundraiser Fundraiser struct
     */
    function getFundraiser(uint256 fundraiserId)
        external
        view
        onlyValidFundraiser(fundraiserId)
        returns (Fundraiser memory fundraiser)
    {
        return fundraisers[fundraiserId];
    }
    
    /**
     * @dev Update fundraiser details (only by creator)
     * @param fundraiserId ID of the fundraiser
     * @param title New title
     * @param description New description
     */
    function updateFundraiser(
        uint256 fundraiserId,
        string memory title,
        string memory description
    )
        external
        onlyValidFundraiser(fundraiserId)
        onlyCreator(fundraiserId)
        onlyActiveFundraiser(fundraiserId)
    {
        require(bytes(title).length > 0, "Title cannot be empty");
        require(bytes(description).length > 0, "Description cannot be empty");
        
        fundraisers[fundraiserId].title = title;
        fundraisers[fundraiserId].description = description;
        
        emit FundraiserUpdated(fundraiserId, title, description);
    }
    
    /**
     * @dev Add donation to fundraiser (called by donation contract)
     * @param fundraiserId ID of the fundraiser
     * @param amount Donation amount in wei
     */
    function addDonation(uint256 fundraiserId, uint256 amount)
        external
        onlyValidFundraiser(fundraiserId)
        onlyActiveFundraiser(fundraiserId)
    {
        require(amount > 0, "Donation amount must be greater than 0");
        
        fundraisers[fundraiserId].currentAmount += amount;
        fundraisers[fundraiserId].donationCount++;
        
        // Check if goal is reached
        if (fundraisers[fundraiserId].currentAmount >= fundraisers[fundraiserId].goalAmount) {
            _completeFundraiser(fundraiserId);
        }
    }
    
    /**
     * @dev Complete a fundraiser
     * @param fundraiserId ID of the fundraiser
     */
    function completeFundraiser(uint256 fundraiserId)
        external
        onlyValidFundraiser(fundraiserId)
        onlyCreator(fundraiserId)
        onlyActiveFundraiser(fundraiserId)
    {
        _completeFundraiser(fundraiserId);
    }
    
    /**
     * @dev Deactivate a fundraiser
     * @param fundraiserId ID of the fundraiser
     */
    function deactivateFundraiser(uint256 fundraiserId)
        external
        onlyValidFundraiser(fundraiserId)
        onlyCreator(fundraiserId)
        onlyActiveFundraiser(fundraiserId)
    {
        fundraisers[fundraiserId].isActive = false;
        
        emit FundraiserDeactivated(fundraiserId, msg.sender);
    }
    
    /**
     * @dev Get fundraisers by creator
     * @param creator Address of the creator
     * @return fundraiserIds Array of fundraiser IDs
     */
    function getFundraisersByCreator(address creator)
        external
        view
        returns (uint256[] memory fundraiserIds)
    {
        return creatorFundraisers[creator];
    }
    
    /**
     * @dev Get active fundraisers
     * @return activeFundraisers Array of active fundraiser IDs
     */
    function getActiveFundraisers()
        external
        view
        returns (uint256[] memory activeFundraisers)
    {
        uint256 count = 0;
        
        // Count active fundraisers
        for (uint256 i = 1; i <= fundraiserCounter; i++) {
            if (fundraisers[i].isActive && !fundraisers[i].isCompleted) {
                count++;
            }
        }
        
        // Create array and populate
        activeFundraisers = new uint256[](count);
        uint256 index = 0;
        
        for (uint256 i = 1; i <= fundraiserCounter; i++) {
            if (fundraisers[i].isActive && !fundraisers[i].isCompleted) {
                activeFundraisers[index] = i;
                index++;
            }
        }
        
        return activeFundraisers;
    }
    
    /**
     * @dev Get fundraiser progress percentage
     * @param fundraiserId ID of the fundraiser
     * @return progress Progress percentage (0-100)
     */
    function getFundraiserProgress(uint256 fundraiserId)
        external
        view
        onlyValidFundraiser(fundraiserId)
        returns (uint256 progress)
    {
        Fundraiser memory fundraiser = fundraisers[fundraiserId];
        
        if (fundraiser.goalAmount == 0) {
            return 0;
        }
        
        return (fundraiser.currentAmount * 100) / fundraiser.goalAmount;
    }
    
    /**
     * @dev Check if fundraiser is expired
     * @param fundraiserId ID of the fundraiser
     * @return isExpired True if expired
     */
    function isFundraiserExpired(uint256 fundraiserId)
        external
        view
        onlyValidFundraiser(fundraiserId)
        returns (bool isExpired)
    {
        return block.timestamp > fundraisers[fundraiserId].endDate;
    }
    
    /**
     * @dev Get total number of fundraisers
     * @return total Total number of fundraisers
     */
    function getTotalFundraisers()
        external
        view
        returns (uint256 total)
    {
        return fundraiserCounter;
    }
    
    /**
     * @dev Internal function to complete a fundraiser
     * @param fundraiserId ID of the fundraiser
     */
    function _completeFundraiser(uint256 fundraiserId) internal {
        fundraisers[fundraiserId].isCompleted = true;
        fundraisers[fundraiserId].isActive = false;
        
        emit FundraiserCompleted(
            fundraiserId,
            fundraisers[fundraiserId].currentAmount,
            fundraisers[fundraiserId].donationCount
        );
    }
}
