/**
 * Smart Contract Deployment Script for ReliePH
 * Deploy DonationContract and FundraiserContract to Ethereum network
 * 
 * Prerequisites:
 * 1. Install Node.js and npm
 * 2. Install Hardhat: npm install --save-dev hardhat
 * 3. Install dependencies: npm install @nomiclabs/hardhat-ethers ethers
 * 4. Set up environment variables in .env file
 */

const { ethers } = require("hardhat");

async function main() {
    console.log("🚀 Starting ReliePH Smart Contract Deployment...");
    
    // Get the deployer account
    const [deployer] = await ethers.getSigners();
    console.log("Deploying contracts with account:", deployer.address);
    
    // Check deployer balance
    const balance = await deployer.getBalance();
    console.log("Account balance:", ethers.utils.formatEther(balance), "ETH");
    
    if (balance.lt(ethers.utils.parseEther("0.01"))) {
        console.log("❌ Insufficient balance for deployment. Please add ETH to your account.");
        return;
    }
    
    try {
        // Deploy DonationContract
        console.log("\n📝 Deploying DonationContract...");
        const DonationContract = await ethers.getContractFactory("DonationContract");
        const donationContract = await DonationContract.deploy();
        await donationContract.deployed();
        
        console.log("✅ DonationContract deployed to:", donationContract.address);
        console.log("   Transaction hash:", donationContract.deployTransaction.hash);
        
        // Deploy FundraiserContract
        console.log("\n📝 Deploying FundraiserContract...");
        const FundraiserContract = await ethers.getContractFactory("FundraiserContract");
        const fundraiserContract = await FundraiserContract.deploy();
        await fundraiserContract.deployed();
        
        console.log("✅ FundraiserContract deployed to:", fundraiserContract.address);
        console.log("   Transaction hash:", fundraiserContract.deployTransaction.hash);
        
        // Verify contracts (optional - requires verification service)
        console.log("\n🔍 Verifying contracts...");
        try {
            await hre.run("verify:verify", {
                address: donationContract.address,
                constructorArguments: [],
            });
            console.log("✅ DonationContract verified");
        } catch (error) {
            console.log("⚠️ DonationContract verification failed:", error.message);
        }
        
        try {
            await hre.run("verify:verify", {
                address: fundraiserContract.address,
                constructorArguments: [],
            });
            console.log("✅ FundraiserContract verified");
        } catch (error) {
            console.log("⚠️ FundraiserContract verification failed:", error.message);
        }
        
        // Save contract addresses to file
        const contractAddresses = {
            network: hre.network.name,
            donationContract: donationContract.address,
            fundraiserContract: fundraiserContract.address,
            deployer: deployer.address,
            deploymentTime: new Date().toISOString(),
            transactionHashes: {
                donationContract: donationContract.deployTransaction.hash,
                fundraiserContract: fundraiserContract.deployTransaction.hash
            }
        };
        
        const fs = require('fs');
        fs.writeFileSync(
            'contract_addresses.json', 
            JSON.stringify(contractAddresses, null, 2)
        );
        
        console.log("\n🎉 Deployment completed successfully!");
        console.log("\n📋 Contract Addresses:");
        console.log("   DonationContract:", donationContract.address);
        console.log("   FundraiserContract:", fundraiserContract.address);
        console.log("\n💾 Addresses saved to contract_addresses.json");
        
        console.log("\n🔧 Next Steps:");
        console.log("1. Update your .env file with the contract addresses:");
        console.log(`   DONATION_CONTRACT_ADDRESS=${donationContract.address}`);
        console.log(`   FUNDRAISER_CONTRACT_ADDRESS=${fundraiserContract.address}`);
        console.log("2. Update your database with the contract addresses");
        console.log("3. Test the contracts with sample transactions");
        
    } catch (error) {
        console.error("❌ Deployment failed:", error);
        process.exit(1);
    }
}

// Execute deployment
main()
    .then(() => process.exit(0))
    .catch((error) => {
        console.error(error);
        process.exit(1);
    });
