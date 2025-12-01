// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract IPFS_CID_STORAGE {
    struct Data {
        uint256 timestamp;
        string title;
        string metadata;
        string cid;
    }

    // Share CID to other Address
    struct Shared{
        uint256 timestamp;
        string cid;
        string message;
    }
    
    //Sender => userData
    mapping(address => Data[]) private userData; // Mapping from address to array of Data structs)

        // sender => receiver => [Shared data]
    mapping(address => mapping(address => Shared[])) private sharedCID;

    // sender => [list of unique receivers]
    mapping(address => address[]) private senderReceivers;

    event DataStored(address indexed user, uint256 timestamp, string title, string metadata, string cid);

    function storeData(string memory _title,string memory _metadata, string memory _cid ) public {
        if (bytes(_title).length == 0) {
            revert ("EmptyTitle");
        }
        if (bytes(_metadata).length == 0) {
            revert ("EmptyMetadata");
        }
        if (bytes(_cid).length == 0) {
            revert ("EmptyCID");
        }
        userData[msg.sender].push(Data(block.timestamp, _title, _metadata, _cid)); // Store data with timestamp
        emit DataStored(msg.sender, block.timestamp, _title, _metadata, _cid);
    }

    function transferCID(address _toReceiver, string memory _cid, string memory _msg) public {
        if (_toReceiver == address(0) || _toReceiver == msg.sender) {
            revert("Invalid receiver");
        }
        if (bytes(_cid).length <= 0) {
            revert("CID cannot be empty");
        }
        Data[] memory dataList = userData[msg.sender];
        address[]  memory saved_address = senderReceivers[msg.sender];
        uint256 index;
        bool address_exist = false;
        bool cid_exist = false;
        for (uint256 i = 0; i < saved_address.length; i++) {
            if (saved_address[i] == _toReceiver) {
                index = i;
                address_exist = true;
                break;
            }
        }

        for (uint256 i = 0; i < dataList.length; i++) {
            if (keccak256(bytes(dataList[i].cid)) == keccak256(bytes(_cid))) {
                index = i;
                cid_exist = true;
                break;
            }
        }
        if(!cid_exist){
            revert ("cid does not exist");
        }
        // Add to sender's receiver list if not exist (for enumeration)
        if(!address_exist){
            senderReceivers[msg.sender].push(_toReceiver);
        }
        
        Data memory data = dataList[index];
        userData[_toReceiver].push(Data(block.timestamp, data.title, data.metadata, data.cid)); // Store data with timestamp
        sharedCID[msg.sender][_toReceiver].push(Shared(block.timestamp, data.cid, _msg));

        emit DataStored(msg.sender, block.timestamp, data.title, data.metadata, _cid);
    }

    function retrieveData(uint256 _index)
    public view returns (uint256, string memory, string memory, string memory) {
        if(_index > userData[msg.sender].length){
            revert ("InvalidIndex");
        }
        Data memory data = userData[msg.sender][_index];
        return (data.timestamp, data.title, data.metadata, data.cid);
    }

    function getDataCount() public view returns (uint256) {
        return userData[msg.sender].length;
    }

    function getReceivers() public view returns (address[] memory) {
        return senderReceivers[msg.sender];
    }

    function getShareCount(address _sender, address _toReceiver) public view returns (uint256) {
        return sharedCID[_sender][_toReceiver].length;
    }

    function getShareHistory(address _sender, address _toReceiver, uint256 _index) public view returns (uint256, string memory, string memory) {
        Shared memory data = sharedCID[_sender][_toReceiver][_index];
        return (data.timestamp, data.cid, data.message);
    }

}