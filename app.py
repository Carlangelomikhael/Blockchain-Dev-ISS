import json
import time
from datetime import timedelta
from hashlib import sha256
from flask import Flask, request, render_template, session, url_for, redirect, send_from_directory, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Column, Integer, String
import rsa
import pickle
import secrets
import os.path


# Block Class with it's basic attributes
# We have the block's index, transaction (between nodes) , timestamp (when it was created)
# the hash of the previous block and the nonce (number used once)
class Block:
    def __init__(self, index, transaction, timestamp, previous_hash, nonce=0):
        self.index = index
        self.transaction = transaction
        self.timestamp = timestamp
        self.previous_hash = previous_hash
        self.nonce = nonce

    # Function that take as an input all the block's attributes
    # and outputs the hash of the block (encoded in sha256)
    def compute_hash(self):
        # json.dumps => Converts a Python object into a json string
        # self.__dict__ => all attributes defined for the object Block
        block_string = json.dumps(self.__dict__)

        # encode() => Encode the json string
        # sha256() => Hash it with sha256
        # hexdigest() => Returns the encoded data in hexadecimal format
        return (sha256(block_string.encode())).hexdigest()


# Blockchain Class with it's basic attributes
class Blockchain:
    # Arbitrary difficulty of our PoW algorithm (i recommend to change it between 4 and 6)
    diff = 5

    def __init__(self):
        self.unconfirmed_transactions = []
        self.chain = []

    # Function that creates the genesis block
    # and adds it to the blockchain
    def create_genesis_block(self):
        # 0 index, no transactions, the block's timestamp, the block's previous hash (0 because non existent)
        genesis_block = Block(0, b'', time.time(), "0")
        # Calculating the genesis block hash
        genesis_block.hash = genesis_block.compute_hash()
        # Appending the genesis block to the blockchain list
        self.chain.append(genesis_block)
        # Creating a Block_data object (Object of the Block table in the database)
        elmnt = Block_data(0, "", genesis_block.timestamp, "0", 0, genesis_block.hash)

        return elmnt

    # Getter method
    @property
    # Function that gets the last block in the blockchain
    def last_block(self):
        return self.chain[-1]

    # Function that adds new transactions to the unconfirmed transactions list
    def add_new_transaction(self, transaction):
        self.unconfirmed_transactions.append(transaction)

    # Function that mines a block
    def mine(self):

        last_block = self.last_block

        # Creating new block
        new_block = Block(index=last_block.index + 1,
                          transaction=self.unconfirmed_transactions[0],
                          timestamp=time.time(),
                          previous_hash=last_block.hash)

        # Proof is the returned computed hash from the PoW algorithm
        proof = self.proof_of_work(new_block)
        # Adding the newly mined block with it's hash to the blockchain
        self.add_block(new_block, proof)
        return True

    # Function that adds a block to the blockchain
    def add_block(self, block, proof):

        previous_hash = self.last_block.hash

        # Verifying if the previous hash referred in the block
        # and the hash of latest block in the chain match
        if previous_hash != block.previous_hash:
            return False

        # Verifying if the proof is valid
        if not self.is_valid_proof(block, proof):
            return False

        # Adding the block's hash
        block.hash = proof
        self.chain.append(block)
        return True

    # POW algorithm
    def proof_of_work(self, block):
        # Initialising the block's nonce
        block.nonce = 0
        # Computed hash with nonce = 0
        computed_hash = block.compute_hash()

        # While loop that that increments the value of the nonce to get a hash
        # that satisfies our difficulty criteria
        # the criteria it's how many zero's the computed hash starts with
        # if diff = 4 we want a hash that starts with 4 zeros
        while not computed_hash.startswith('0' * self.diff):
            block.nonce += 1
            # Recalculating the hash with different nonce (different input) => (different output/hash)
            computed_hash = block.compute_hash()
            # Uncomment the below print statement to visualise the computed hashes (it will slow down the code eventually)
            '''print(computed_hash)'''
        return computed_hash

    # Function that checks if the proof is valid
    def is_valid_proof(self, block, block_hash):

        # Check if the block's hash is valid and satisfies
        # the difficulty criteria.
        return (block_hash.startswith('0' * self.diff) and
                block_hash == block.compute_hash())


# Node Class with it's basic attributes
# The person's id, the node's index, when he registered, how much currency he holds
# the node's password (encypted with sha256)
# and the newest_chain_copy attribute (takes 2 values: 0 or 1/ 0 = not newest chain copy , 1 = newest chain copy)
class Node:
    def __init__(self, node_id, nodes_number, timestamp, money_amount, pubkey, password, newest_chain_copy,
                 pending_money_amount):
        self.node_id = node_id
        self.nodes_number = nodes_number
        self.timestamp = timestamp
        self.money_amount = money_amount
        self.pubkey = pubkey
        self.password = password
        self.newest_chain_copy = newest_chain_copy
        self.pending_money_amount = pending_money_amount


class Unconfirmed_Transaction:
    def __init__(self, inputs, outputs, signature, transaction_id):
        self.inputs = inputs
        self.outputs = outputs
        self.signature = signature
        self.transaction_id = transaction_id


class Transaction:
    def __init__(self, inputs, outputs, signature, transaction_id):
        self.inputs = inputs
        self.outputs = outputs
        self.signature = signature
        self.transaction_id = transaction_id


# Flask app initialisation
# Templates is the template folder containing all the html/css
app = Flask(__name__, template_folder="templates")


# Function That Reconstructs The Blockchain Chain
def reconstruct_blockchain():
    blockchain.chain = []
    # Querying the full chain from the database (list containing Block_data objects)
    # from the database and transforming it to a list containing Block objects and returning it
    chain_data = get_chain_data()
    for blocks in chain_data:
        reconstructed_block = reconstruct_block(blocks.index, blocks.transactions, blocks.timestamp,
                                                blocks.previous_hash, blocks.nonce, blocks.hash)
        blockchain.chain.append(reconstructed_block)
    return blockchain.chain


# Function That Reconstructs The Block Object (creating a Block object and returning it)
def reconstruct_block(index, transactions, timestamp, previous_hash, nonce, block_hash):
    block = Block(index, transactions, timestamp, previous_hash, nonce)
    block.hash = block_hash
    return block


# Initialize the Blockchain object
blockchain = Blockchain()

# Our application's configurations:
# The database relative path and it's type (sqlite)
# Track modifications is set to false because it adds significant overhead
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///test.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

''' Note: you can change the database uri to 'postgresql://user:password@localhost/your_database_name' 
if you want to work with the postgres database'''

# Generating random 1028 bytes key (1371 character)
generated_key = secrets.token_urlsafe(1028)

# The app's secret key is the key that encrypts the session data
# (very crucial and has to be random for more secure data)
app.secret_key = generated_key

# This config let's us set how much time we want the fetched data
# to be stored in the session
app.permanent_session_lifetime = timedelta(hours=1)

# Our model
db = SQLAlchemy(app)


# Block_data Class with it's basic attributes
# id is an obligatory attribute set by the database
# we have the same attributes as the Block class defined above
class Block_data(db.Model):
    __tablename__ = "Blocks"
    id = Column('id', Integer, primary_key=True)
    index = Column('index', Integer)
    transactions = Column('transactions', String)
    timestamp = Column('timestamp', Integer)
    previous_hash = Column('previous_hash', String)
    nonce = Column('nonce', Integer)
    hash = Column('hash', String)

    def __init__(self, index, transactions, timestamp, previous_hash, nonce, hash):
        self.index = index
        self.transactions = transactions
        self.timestamp = timestamp
        self.previous_hash = previous_hash
        self.nonce = nonce
        self.hash = hash


# Nodes_data Class with it's basic attributes
# id is an obligatory attribute set by the database
# we have the same attributes as the Node class defined above
class Nodes_data(db.Model):
    __tablename__ = "Nodes"
    id = Column('id', Integer, primary_key=True)
    node_id = Column('node_id', String)
    timestamp = Column('timestamp', Integer)
    money_amount = Column('money_amount', Integer)
    pubkey = Column('pubkey', String)
    password = Column('password', String)
    newest_chain_copy = Column('newest_chain_copy', Integer)
    pending_money_amount = Column('pending_money_amount', Integer)

    def __init__(self, node_id, timestamp, money_amount, pubkey, password, newest_chain_copy, pending_money_amount):
        self.node_id = node_id
        self.timestamp = timestamp
        self.money_amount = money_amount
        self.pubkey = pubkey
        self.password = (sha256(password.encode())).hexdigest()
        self.newest_chain_copy = newest_chain_copy
        self.pending_money_amount = pending_money_amount


# Confirmed Transactions Class with it's basic attributes
# id is an obligatory attribute set by the database
# we have the serialized transaction object
class Transactions(db.Model):
    __tablename__ = "Transactions"
    id = Column('id', Integer, primary_key=True)
    inputs = Column('inputs', String)
    outputs = Column('outputs', String)
    signature = Column('signature', String)
    transaction_id = Column('transaction_id', String)

    def __init__(self, inputs, outputs, signature, transaction_id):
        self.inputs = inputs
        self.outputs = outputs
        self.signature = signature
        self.transaction_id = transaction_id


# Unconfirmed_transactions Class with it's basic attributes
# id is an obligatory attribute set by the database
# we have the serialized transaction object
class Unconfirmed_transactions(db.Model):
    __tablename__ = "Unconfirmed_transactions"
    id = Column('id', Integer, primary_key=True)
    inputs = Column('inputs', String)
    outputs = Column('outputs', String)
    signature = Column('signature', String)
    transaction_id = Column('transaction_id', String)

    def __init__(self, inputs, outputs, signature, transaction_id):
        self.inputs = inputs
        self.outputs = outputs
        self.signature = signature
        self.transaction_id = transaction_id


# Function that adds element to the database
def add_element(elmnt):
    db.session.add(elmnt)
    db.session.commit()


# Function that queries the database and return a list of all the blocks (Block_data objects)
def get_chain_data():
    return db.session.query(Block_data).all()


# Function that queries the database and return a list of all the nodes (Nodes_data objects)
def get_nodes():
    return db.session.query(Nodes_data).all()


# Function that queries the database and return a list of all the unconfirmed transaction (Unconfirmed_transactions objects)
# then we iterate through the returned list and we de-serialize the objects (because they are stored in bytes)
# by using pickle.loads and we return the new list containing de-serialized Unconfirmed_transactions objects
def get_unconf_tx():
    unconf_transactions = db.session.query(Unconfirmed_transactions).all()
    unconf_tx_list = []
    for transaction in unconf_transactions:
        unconf_tx_list.append(transaction.transaction_id)
    return unconf_tx_list


# Function that queries the database and return a list of all the blocks (Block_data objects)
# then we iterate through the returned list and we reconstruct the blockchain by reconstructing every block object
# and adding them to the chain attribute of the Blockchain object
def get_blockchain():
    chain = []
    # Retrieving the chain from the database
    chain_data = get_chain_data()
    # Iterating through the list
    for blocks in chain_data:
        # Calling the reconstruct_block function defined above
        reconstructed_block = reconstruct_block(blocks.index, blocks.transactions, blocks.timestamp,
                                                blocks.previous_hash, blocks.nonce, blocks.hash)
        chain.append(reconstructed_block.__dict__)
    return chain


# Function that creates and then adds an unconfirmed transaction to the database
def add_unconfirmed_transactions(tx):
    # Creating a Unconfirmed_transactions object with transaction (tx) as an attribute
    new_transaction = Unconfirmed_transactions(tx.inputs, tx.outputs,
                                               tx.signature, tx.transaction_id)
    add_element(new_transaction)
    db.session.commit()


# Function that deletes an unconfirmed transaction from the database
def delete_unconfirmed_transactions():
    # querying the first Unconfirmed_Transactions object then deleting it
    unconf_tx_to_delete = db.session.query(Unconfirmed_transactions).first()
    db.session.delete(unconf_tx_to_delete)
    db.session.commit()


# Function that computes the transaction id with sha256 encoding
def compute_transaction_id(transaction_sender, transaction_receiver, timestamp, transaction_amount):
    transaction_string = transaction_sender + transaction_receiver + str(timestamp) + str(transaction_amount)
    return (sha256(transaction_string.encode())).hexdigest()


# Function that update the newest_chain_copy attribute of the all the Nodes objects to 0
def change_chain_copy_status_all():
    # Querying the nodes from database (list of Nodes_data objects)
    nodes_list = get_nodes()
    # Iterating through the list and updating the newest_chain_copy values
    for node in nodes_list:
        node.newest_chain_copy = 0
        db.session.commit()


# Function that update the newest_chain_copy attribute of the specified Node object to 1
def node_change_chain_copy_status(node_name):
    # Querying the specified node from database (filtered by the node's name)
    node = Nodes_data.query.filter_by(name=node_name).first()
    # updating the newest_chain_copy value
    node.newest_chain_copy = 1
    db.session.commit()


# Function that query the newest_chain_copy value attribute of the specified Node object then returning it
def get_chain_copy_status(node_id):
    # Querying the specified node from database (filtered by the node's name)
    node = Nodes_data.query.filter_by(node_id=node_id).first()
    status = node.newest_chain_copy
    return status


# Function that gets the transaction sender , receiver and the amount from the transaction id and return them in a list
# by iterating through the list of registered nodes and computing every pair of nodes (sender and receiver)
# to get the right transaction id
def get_sender_receiver_amount():
    # Getting the first transaction in the database (transaction that will be saved in the next mined block)
    transaction = db.session.query(Unconfirmed_transactions).first()
    # Querying the database and getting the list of the nodes
    nodes_list = get_nodes()
    # Iterating through the list
    for node1 in nodes_list:
        for node2 in nodes_list:
            if node1.name != node2.name:
                transaction_sender = node1.name
                transaction_receiver = node2.name
                result = sha256((transaction_sender + transaction_receiver).encode()).hexdigest()
                index = transaction.transaction_id.find('/')
                amount = transaction.transaction_id[index + 1:]
                # Checking if transaction id and the computed sha256 string match
                if result == transaction.transaction_id[:index]:
                    return [transaction_sender, transaction_receiver, amount]


# Function that queries the sender and receiver node of a transaction
# and update their balances and pending money (the sender's pending money is sent to the receiver's wallet)
def change_money_amount(list, block_miner):
    # Querying the specified nodes (sender and receiver and the block miner imputed in the fct args)
    # from database (filtered by the node's name)
    sender = Nodes_data.query.filter_by(name=list[0]).first()
    receiver = Nodes_data.query.filter_by(name=list[1]).first()
    miner = Nodes_data.query.filter_by(name=block_miner).first()
    # Updating the balances (miner gets 10% of the transaction amount)
    sender.pending_money_amount -= int(list[2])
    receiver.money_amount += float(0.9 * int(list[2]))
    miner.money_amount += float(0.1 * int(list[2]))
    db.session.commit()
    # Updating the session data
    session['node_money_amount'] = sender.money_amount
    session['pending_money_amount'] = sender.pending_money_amount


# Function that updates the sender's money amount in his active wallet and in his pending transferred money
# the money is pending and won't be sent until their is a block mined containing the transaction
def update_node_money(transaction_sender, transaction_amount):
    # Querying the sender node from database
    node = Nodes_data.query.filter_by(node_id=transaction_sender).first()
    # Updating the balances
    node.money_amount -= int(transaction_amount)
    node.pending_money_amount += int(transaction_amount)
    db.session.commit()
    # Updating the session data
    session['node_money_amount'] = node.money_amount
    session['pending_money_amount'] = node.pending_money_amount


def get_node_id(name, number_of_node, timestamp):
    node_id = b''
    node_id += name.encode()
    node_id += (str(number_of_node)).encode()
    node_id += (str(timestamp)).encode()

    return sha256(node_id).hexdigest()


''' Warning: the following if statement will launch an error
 if the database is non existent, follow the steps below to create the database:
 - comment out the code below (*)
 - open your command prompt
 - change the current working directory to the directory where the app exist 
 - run 'python' command
 - run 'from app import db' command (app being the name of our file and db our database model)
 - run 'db.create_all()' command
 - run 'exit()' command'''

'''* Comment out if the database is non existent'''
# If statement that checks if the Block_data table is empty
# and creates the genesis block if it's empty
if not db.session.query(Block_data).all():
    add_element(blockchain.create_genesis_block())
    db.session.commit()
    db.session.close()
'''*'''


# endpoint to return the full chain of our blockchain object
@app.route('/chain', methods=['GET'])
def get_chain():
    return render_template('blockchain_chain.html', blockchain_chain=get_blockchain())


# endpoint to get all pending (unconfirmed) transactions
@app.route('/pending_transactions')
def get_pending_transactions():
    # Checking if the user is logged in
    if session.get('logged_in'):
        if not get_unconf_tx():
            return "No pending transactions"
        else:
            return render_template('display_page.html', page=0, object_list=get_unconf_tx())
    else:
        # If user is not logged in we throw a flash warning and redirect him to the signup page
        flash("WARNING: You can't access the pending transactions page without logging in")
        return redirect(url_for('register_node'))


# endpoint to get all pending (unconfirmed) transactions
@app.route('/nodes')
def get_existing_nodes():
    # Checking if the user is logged in
    if session.get('logged_in'):
        if not get_nodes():
            return "No pending transactions"
        else:
            return render_template('display_page.html', page=1, object_list=get_nodes())
    else:
        # If user is not logged in we throw a flash warning and redirect him to the signup page
        flash("WARNING: You can't access the pending transactions page without logging in")
        return redirect(url_for('register_node'))


# endpoint to register a new node
@app.route('/signup', methods=['GET', 'POST'])
def register_node():
    if request.method == 'GET':
        return render_template('signup.html', status=True)
    elif request.method == 'POST':
        name = request.form['Name'].strip()
        password = request.form['Psw'].strip()
        password_repeat = request.form['Psw-repeat'].strip()
        node_list = get_nodes()

        if password == password_repeat:

            # Creating a node class object
            number_of_node = len(node_list) + 1
            timestamp = time.time()
            node_id = get_node_id(name, number_of_node, timestamp)

            node = Node(node_id, number_of_node, timestamp, 100, b'', password, 0, 0)

            # Creating a node_data class object
            # and adding it to the database
            node_data = Nodes_data(node.node_id, node.timestamp, node.money_amount, node.pubkey,
                                   node.password, node.newest_chain_copy, node.pending_money_amount)
            add_element(node_data)

            # Updating all the node's newest_chain_copy values in the database
            change_chain_copy_status_all()

            # Setting the session permanent (1 hour in our case)
            session.permanent = True
            # Saving the node's name, money amount and public key to the session to be able to manipulate the data
            # without querying the database every time
            # Setting logged_in variable to True in order
            # to have access to certain endpoints
            session['node_id'] = node.node_id
            session['node_money_amount'] = node.money_amount
            session['node_public_key'] = node_data.pubkey
            session['pending_money_amount'] = node_data.pending_money_amount
            session['receivers'] = ''
            session['logged_in'] = True

            # Return the signup.html template with arguments (see signup.html)
            return render_template('signup.html', status=False, name=name, Node_nb=number_of_node)
        else:
            # If the imputed passwords don't match we throw a flash error
            flash("Error: Passwords don\'t match")
            return redirect(url_for('register_node'))


# endpoint to signin as a node
@app.route('/signin', methods=['GET', 'POST'])
def signin_page():
    if request.method == 'GET':
        return render_template('signin.html')
    elif request.method == 'POST':
        # Striping the name and password (we don't want to include any of the spaces at the borders of the string)
        # then saving them in variables
        node_id = request.form['node_id'].strip()
        password = request.form['Psw'].strip()

        # Querying the database and returning a list of all the nodes (Nodes_data objects)
        node_list = get_nodes()
        # Checking if node with the inserted name exists
        # Checking if inserted data (in the form) match
        if node_list:
            for node in node_list:
                if node.node_id == node_id:
                    if node.password == (sha256(password.encode())).hexdigest():
                        # Saving the node's name, money amount and public key to the session
                        # Setting logged_in variable to True in order
                        # to have access to certain endpoints
                        session['node_id'] = node_id
                        session['node_money_amount'] = node.money_amount
                        session['pending_money_amount'] = node.pending_money_amount
                        session['node_public_key'] = node.pubkey
                        session['transactions'] = ''
                        session['logged_in'] = True
                    else:
                        # If the imputed data don't match we throw a flash error
                        flash('Error: Invalid login data check your name/password')
                        return redirect(url_for('signin_page'))

                    # If the user is logged in we redirect him to the home page
                    if session.get('logged_in'):
                        return redirect(url_for('home'))

            # If the user attempts to login with a non existent node name we throw a flash error
            # and redirect him to the signup page
            flash('Error: Register before attempting to log in')
            return redirect(url_for('register_node'))
        else:
            # If no node is registered yet we throw a flash error and redirect him to the signup page
            flash("Error: No nodes registered yet")
            return redirect(url_for('register_node'))


# endpoint to download the database containing the blockchain, the registered nodes
# and the unconfirmed transactions
@app.route('/download')
def download_file():
    # Checking if the user is logged in
    if session.get('logged_in'):
        # File to be downloaded
        path = 'database.db'
        # The path where the file exists
        directory = 'C:\\Users\\User\\PycharmProjects\\blockchain'
        node_id = session.get('node_id')
        try:
            # Updating the value of the node's newest_chain_copy attribute
            node_change_chain_copy_status(node_id)
            file_path = 'C:/Users/User/Downloads/database.db'
            # Checking if the file exists , if true we delete it (old copy)
            if os.path.exists(file_path):
                os.remove(file_path)
            # Downloads the database file
            return send_from_directory(directory, path, as_attachment=True)
        except:
            # Downloads the database file
            return send_from_directory(directory, path, as_attachment=True)
    else:
        # If user is not logged in we throw a flash warning and redirect him to the signup page
        flash("WARNING: You can't access the download page without logging in")
        return redirect(url_for('register_node'))


@app.route('/download_config')
def download_config():
    # Checking if the user is logged in
    if session.get('logged_in'):
        # File to be downloaded
        path = 'test_client.py'
        # The path where the file exists
        directory = 'C:\\Users\\User\\PycharmProjects\\blockchain'
        return send_from_directory(directory, path, as_attachment=True)

    else:
        # If user is not logged in we throw a flash warning and redirect him to the signup page
        flash("WARNING: You can't access the download configuration page without logging in")
        return redirect(url_for('register_node'))


@app.route('/download_requirements')
def download_requirements():
    # Checking if the user is logged in
    if session.get('logged_in'):
        # File to be downloaded
        path = 'requirements.txt'
        # The path where the file exists
        directory = 'C:\\Users\\User\\PycharmProjects\\blockchain'
        return send_from_directory(directory, path, as_attachment=True)

    else:
        # If user is not logged in we throw a flash warning and redirect him to the signup page
        flash("WARNING: You can't access the download configuration page without logging in")
        return redirect(url_for('register_node'))


# the welcome page endpoint (before sign in/sign up or after logout)
@app.route('/')
def welcome():
    # Checking if the user is logged in
    # if true we redirect him to the home page else we redirect him to the welcome page
    if session.get('logged_in'):
        return redirect(url_for('home'))
    else:
        return render_template('welcome.html')


# the logout page endpoint
@app.route('/logout')
def logout():
    # Checking if the user is logged in
    # if true we logout the user (deleting the user's session data)
    # and redirect him to the welcome page
    if session.get('logged_in'):
        session.pop('node_id', None)
        session.pop('node_money_amount', None)
        session.pop('pending_money_amount', None)
        session.pop('node_public_key', None)
        session.pop('transaction', None)
        session['logged_in'] = False
    return redirect(url_for('welcome'))


# the home page endpoint (page after login)
@app.route('/home', methods=['GET', 'POST'])
def home():
    # Checking if the user is logged in
    if session.get('logged_in'):
        if request.method == 'GET':
            node_id = session.get('node_id')
            node = Nodes_data.query.filter_by(node_id=node_id).first()
            session['node_money_amount'] = node.money_amount
            session['pending_money_amount'] = node.pending_money_amount
            session['node_id'] = node.node_id
            session['transactions'] = []

            # Returning the home.html template with args to be displayed
            return render_template('home.html', transaction_list=session.get('transactions'),
                                   up_to_date=get_chain_copy_status(node_id))

        if request.method == 'POST':
            # Getting the transaction data and storing it in session values
            transaction_sender = session.get('node_id')
            transaction_receiver = request.form['Receiver']
            transaction_amount = request.form['Amount']
            # Checking if the sender and receiver nodes are the same node
            if transaction_sender == transaction_receiver:
                # Throwing a flash warning if the transaction sender tried
                # to send money to his self
                flash("WARNING: You can't send ISS coins to your self")
                return redirect(url_for('home'))
            else:
                # Setting the receiver value to 0 ( 0 = the receiver node is not registered , 1 = the receiver node is registered)
                receiver = 0
                # Querying the nodes from database (list of Nodes_data objects)
                nodes = get_nodes()
                # Checking if the receiver is a registered node
                for node in nodes:
                    if transaction_receiver == node.node_id:
                        receiver = 1
                if int(transaction_amount) > session.get('node_money_amount'):
                    # Throwing a flash warning if the transaction sender tried
                    # to send more than what he has in his wallet
                    flash("WARNING: You don't have enough funds for this transaction")
                    return redirect(url_for('home'))
                elif receiver == 1:

                    # Creating a string stating the transaction sender, receiver and the amount
                    unconf_tx_str = f'{transaction_sender} wants to send {transaction_amount} ISS coins to {transaction_receiver} '

                    # Trying to open the file containing the receiver's Private Key from the directory where it was saved (saved automatically when the user signup)
                    # and decrypting the transactions with the receiver's private key (if no error is thrown means he's the receiver)
                    directory = f'C:\\Users\\User\\\\Downloads\\{transaction_sender}_private_key'
                    filename = "PrivateKey.txt"
                    file_path = os.path.join(directory, filename)
                    # Opening the Private Key text file in read bytes mode ('rb') the Private Key is stored in bytes
                    # extracting the public key using pickle.load
                    f = open(file_path, "rb")
                    private_key = pickle.load(f)

                    # Encrypting the above string with the receiver's public key (saved in the database)
                    # we encode the string to bytes and de-serialize the receiver's public with pickle.loads
                    signature = rsa.sign(unconf_tx_str.encode(), private_key, 'SHA-256')

                    inputs = {"sender": transaction_sender, "amount": session.get('node_money_amount')}
                    outputs = {"sender": transaction_sender,
                               "remains": session.get('node_money_amount') - int(transaction_amount) - 0.05 * int(
                                   transaction_amount),
                               "receiver": transaction_receiver, "amount": int(transaction_amount)}

                    unconfirmed_transaction = Unconfirmed_Transaction(json.dumps(inputs), json.dumps(outputs),
                                                                      signature,
                                                                      compute_transaction_id(transaction_sender,
                                                                                             transaction_receiver,
                                                                                             time.time(),
                                                                                             transaction_amount))

                    # Querying the database for the unconfirmed transactions list (list of Unconfirmed_Transactions objects)
                    # saving it in the blockchain's chain attribute
                    blockchain.unconfirmed_transactions = get_unconf_tx()
                    # Adding the new transaction to the blockchain's chain
                    blockchain.add_new_transaction(unconfirmed_transaction)
                    # Adding the new transaction to the Unconfirmed_Transactions table in the database
                    add_unconfirmed_transactions(unconfirmed_transaction)

                    session['transactions'].append(outputs)

                    # Updating all the node's newest_chain_copy values in the database
                    change_chain_copy_status_all()

                    # Updating the sender's balances
                    update_node_money(transaction_sender, transaction_amount)

                    # If all the transaction data is valid we throw a flash message
                    # saying that the transaction is pending (waiting for a node to mine a block containing the transaction)
                    flash("Pending Transaction")
                    # Returning the home.html template with args to be displayed
                    return render_template('home.html', transaction_list=session.get('transactions'),
                                           up_to_date=get_chain_copy_status((session.get('node_id'))))

                # return redirect(url_for('home'))

                # If user submits a new transaction and the receiving node doesn't exist
                flash("Error: The Node You Are Trying To Send Money To Doesn't Exist")
                return redirect(url_for('home'))

    else:
        # If user is not logged in we throw a flash warning and redirect him to the signup page
        flash("WARNING: You can't access the home page without logging in")
        return redirect(url_for('register_node'))


# Running the app with host="0.0.0.0" enables all the the devices with the same IPv4 (public ip)
# as you to view the app and interact with the blockchain (create user, send transaction ...)
if __name__ == '__main__':
    app.run(host="0.0.0.0")
