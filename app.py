from flask import Flask, flash, jsonify, request, send_file, session, render_template, url_for, redirect, Response, stream_with_context, after_this_request
import shutil
import smart_contract as web3
import ipfs
import file_handler as handler
import os, json
from measure import performance_measure, stringify_report, metrics_to_csv
# import psutil

from dotenv import load_dotenv
load_dotenv()
# Flask app setup
app = Flask(__name__)
app.secret_key = os.urandom(24)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['DOWNLOAD_FOLDER'] = 'downloads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['DOWNLOAD_FOLDER'], exist_ok=True)

# IPFS Pinner Setup
ipfs_cluster_node = os.getenv('IPFS_CLUSTER_NODE', "[]")
ipfs_node = None
# Web3 Contract Setup

contract = handler.load_contract_info("contracts/contract_info.json")
web3_contract = web3.address_storage_contract(contract['abi'], contract['address'])




@app.route('/')
def index():
    return render_template('index.html')

# Signup Tutorial Endpoints
@app.route('/signup')
def signup():
    return redirect("http://10.6.6.11:5000/", code=302)

# Login Endpoints
@app.route('/login')
def login():
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# Login Session Submission
@app.route('/login_submit', methods=['POST'])
def login_submit():
    address = request.form.get('address')
    private_key = request.form.get('private_key')

    if web3_contract.verify_key_pair(address, private_key):
        session['Login'] = True
        session['address'] = address
        session['private_key'] = private_key
        return redirect(url_for('dashboard'))
    else:
        flash('Invalid key pair. Please try again.')
        return redirect(url_for('login'))

# Main Dashboard
@app.route('/dashboard')
def dashboard():
    try:
        if not session['Login']:
            return redirect(url_for('login'))
        return render_template('dashboard.html')
    except Exception as e:
        print(e)
        return redirect(url_for('login'))
    # return render_template('dashboard.html')

# File Upload Endpoint
@app.route('/upload_file', methods=['POST'])
def upload_file():
    measure_http = performance_measure(monitor_interval=0.1)
    measure_http.start()
    print("Sending file")
    # Validate request and save file BEFORE streaming begins
    if 'file' not in request.files:
        measure_http.end(lambda: None)
        return Response(json.dumps({'status': 'error', 'message': 'No file part'}) + "\n", mimetype="application/json")

    file = request.files.get("file")
    if file is None or file.filename == '':
        measure_http.end(lambda: None)
        return Response(json.dumps({'status': 'error', 'message': 'No selected file'}) + "\n", mimetype="application/json")

    if handler.is_unallowed_file(file.filename):
        measure_http.end(lambda: None)
        return Response(json.dumps({'status': 'error', 'message': 'File type not allowed'}) + "\n", mimetype="application/json")

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
    measure_http.end(file.save,file_path)
    http_report = stringify_report(measure_http.measure())
    metrics_to_csv(measure_http.measure(), "logs/metrics_http.csv", process_name="http_transfer", size_bytes=handler.extract_file_size(file_path))
    print("server successfully received file")
    print(http_report)
    # Capture everything needed from the request/session up front
    address = session.get('address')
    private_key = session.get('private_key')

    def upload_process():
        try:
            yield json.dumps({'status': 'processing', 'message': 'File received, processing...'}) + "\n"
            measure_ipfs_upload = performance_measure(monitor_interval=0.5)

            measure_ipfs_upload.start()

            cid = ipfs.upload_to_ipfs(file_path)

            title, metadata = handler.extract_meta(file_path)

            if cid is None:
                try:
                    os.remove(file_path)
                except Exception:
                    pass
                measure_ipfs_upload.end(lambda: None)  # Stop measuring
                yield json.dumps({'status': 'error', 'message': 'Error uploading file to IPFS'}) + "\n"
                return

            yield json.dumps({'status': 'processing', 'message': f'CID published, CID: {cid}'}) + "\n"
            print(f'File Sent, CID: {cid}')

            yield json.dumps({'status': 'processing', 'message': 'Storing data on blockchain...'}) + "\n"



            tx_receipt = web3_contract.store_data(
                title,
                metadata,
                cid,
                address,
                private_key
                # ,request.form.get('gas')
            )

            if tx_receipt is None:
                try:
                    os.remove(file_path)
                except Exception:
                    pass
                gc = ipfs.garbage_collect_ipfs()
                print("garbage collected :")
                print(gc)
                measure_ipfs_upload.end(lambda: None)
                yield json.dumps({'status': 'error', 'message': 'Error storing file data on blockchain '}) + "\n"
                return

            yield json.dumps({'status': 'processing', 'message': 'Storing data on blockchain...'}) + "\n"
            print(tx_receipt)
            print("transaction done")
            yield json.dumps({'status': 'processing', 'message': f'{tx_receipt} - Transaction done'}) + "\n"

            yield json.dumps({'status': 'processing', 'message': 'Pinning file on IPFS...'}) + "\n"


            # pin = ipfs.pin_to_ipfs(cid, ipfs_node)
            pin = measure_ipfs_upload.end(ipfs.pin_to_ipfs_cluster, cid, ipfs_node)
            report = measure_ipfs_upload.measure()
            metrics_to_csv(report, "logs/metrics.csv", process_name="upload", size_bytes=handler.extract_file_size(file_path))
            if pin is None:
                try:
                    os.remove(file_path)
                except Exception:
                    pass

                yield json.dumps({'status': 'error', 'message': 'Error pinning file on IPFS. Pinning service may be down.'}) + "\n"
                return
            print(pin)

            yield json.dumps({'status': 'info', 'message': stringify_report(report)}) + "\n"
            gc = ipfs.garbage_collect_ipfs()
            print(f"garbage collected : {gc}")
            try:
                os.remove(file_path)
            except Exception:
                pass
            yield json.dumps({'status': 'success', 'message': 'File Successfully Stored in IPFS!'}) + "\n"
        except Exception as e:
            # Emit an error line if anything unexpected happens
            yield json.dumps({'status': 'error', 'message': f'Unexpected error: {str(e)}'}) + "\n"

    return Response(stream_with_context(upload_process()), mimetype="application/json")

# File Upload Endpoint
@app.route('/share_file',)
def share_file():

    # Validate request and save file BEFORE streaming begins

    receiver = request.args.get('address')
    message = request.args.get('message')
    cid = request.args.get('cid')


    print(f"receiver: {receiver}, message: {message}, cid: {cid}")
    print("Sharing file")
    if web3_contract.is_address(receiver) is False:
        return Response(json.dumps({'status': 'error', 'message': 'Invalid address EIP-55 checksum'}) + "\n", mimetype="application/json")
    print("Address verified")
    # Capture everything needed from the request/session up front
    address = session.get('address')
    private_key = session.get('private_key')

    def sharing_process():
        try:
            yield json.dumps({'status': 'processing', 'message': f'Sending CID: {cid}, processing...'}) + "\n"
            print(f'File Sent, CID: {cid}')

            yield json.dumps({'status': 'processing', 'message': 'Storing data on blockchain...'}) + "\n"

            tx_receipt = web3_contract.share_cid(
                receiver,
                cid,
                message,
                address,
                private_key
                # ,request.form.get('gas')
            )

            if tx_receipt is None:
                yield json.dumps({'status': 'error', 'message': 'Error blockchain transaction'}) + "\n"
                return

            yield json.dumps({'status': 'processing', 'message': 'Storing data on blockchain...'}) + "\n"
            print(tx_receipt)
            print("transaction done")
            yield json.dumps({'status': 'processing', 'message': f'{tx_receipt} - Transaction done'}) + "\n"



            yield json.dumps({'status': 'success', 'message': 'File Successfully Shared!'}) + "\n"
        except Exception as e:
            # Emit an error line if anything unexpected happens
            yield json.dumps({'status': 'error', 'message': f'Unexpected error: {str(e)}'}) + "\n"

    return Response(stream_with_context(sharing_process()), mimetype="application/json")

# # Fetch all data from blockchain
@app.route('/api/get_stored_data')
def get_stored_data():
    data = web3_contract.retrieve_all_data(session['address'])
    return jsonify({
        "dt": [str(t) for t in data['dt']],
        "title": data['title'],
        "metadata": data['metadata'],
        "cid": data['cid'],
    })

@app.route('/api/get_address_list')
def get_address_list():
    data = web3_contract.get_account_receiver(session['address'])
    return jsonify({
        "address": data,
    })

@app.route('/api/get_send_history')
def get_send_history():
    receiver_address = request.args.get('address')
    print(f"Fetching history to {receiver_address}")
    print(session['address'])
    data = web3_contract.get_all_history(session['address'], receiver_address)
    return jsonify({
        "dt": [str(t) for t in data['dt']],
        "cid": data['cid'],
        "message": data['message'],
        "receiver": data['receiver'],
    })


# # Fetch data from blockchain (latest only)
@app.route('/api/data_latest')
def data_latest():
    try:
        latest = web3_contract.retrieve_latest_data(session['address'])
        # Expecting tuple: (timestamp, title, metadata, cid)
        if not latest or len(latest) < 4:
            return jsonify({"error": "No data available"}), 404
        ts, title, metadata, cid = latest
        return jsonify({
            "dt": ts,
            "title": title,
            "metadata": metadata,
            "cid": cid,
        })
    except Exception as e:
        print(f"data_latest error: {e}")
        return jsonify({"error": "Failed to fetch latest data"}), 500


@app.route("/download/initiate")
def download_request():
    cid = request.args.get("cid")

    def stream_progress():
        measure = performance_measure(monitor_interval=0.5)
        measure.start()
        if not cid:
            measure.end(lambda: None)  # Stop measuring
            yield json.dumps({"status":"error","message":"No CID"}) + "\n"
            return
        yield json.dumps({"status":"fetching","message":"Fetching from IPFS..."}) + "\n"
        # path = ipfs.download_from_ipfs(cid, app.config['DOWNLOAD_FOLDER'])

        path = measure.end(ipfs.download_from_ipfs, cid, app.config['DOWNLOAD_FOLDER'])
        report = stringify_report(measure.measure())

        if not path:
            yield json.dumps({"status":"error","message":"Failed to fetch"}) + "\n"
            return

        file_name = os.path.basename(path)
        root_cid = cid.strip("/").split("/")[0] if cid else ""
        metrics_to_csv(measure.measure(), "logs/metrics.csv", process_name="download", size_bytes=handler.extract_file_size(path))


        yield json.dumps({"status":"info","message":report}) + "\n"

        yield json.dumps({
            "status":"success",
            "message":"Download ready",
            "name": file_name,
            "cid": root_cid,
            "download": f"/download/file?cid={root_cid}&name={file_name}"
        }) + "\n"



    return Response(stream_with_context(stream_progress()), mimetype="application/json")

@app.route("/download/file")
def download_file():
    raw_cid = request.args.get("cid")
    name = request.args.get("name")
    if not raw_cid or not name:
        return jsonify({"status": "error", "message": "Missing cid or name"}), 400

    root_cid = raw_cid.strip("/").split("/")[0]
    download_root = app.config.get("DOWNLOAD_FOLDER", "downloads")
    saved_path = os.path.join(download_root, root_cid, name)

    if not os.path.exists(saved_path):
        return jsonify({"status": "error", "message": "File not found"}), 404


    parent_dir = os.path.dirname(saved_path)

    def cleanup_download():
        try:
            print("Cleaning up")
            if os.path.exists(saved_path):
                os.remove(saved_path)
            if os.path.commonpath([parent_dir]) != os.path.commonpath([download_root]):
                shutil.rmtree(parent_dir, ignore_errors=True)
        except Exception as e:
            print(f"Cleanup error: {e}")

    response = send_file(saved_path, as_attachment=True, download_name=name)
    response.direct_passthrough = False
    response.call_on_close(cleanup_download)
    return response



if __name__ == "__main__":
    print(f'{f"="*20} BNPI Data Storage {f"="*21}')
    print("Starting Flask App...")
    for node in json.loads(ipfs_cluster_node):
        if ipfs.cluster_test(node):
            ipfs_node = node
            break
    print(f"Ipfs Pin Node: {ipfs_node}")
    print(f"Contract Address: {contract['address']}")
    print(f"{'connected' if web3_contract.is_connected()['status'] else 'not connected'} to Web3 provider on chain ID {web3_contract.is_connected()['chain_id']}")
    # Connection Test to IPFS Cluster


    print(f"{'='*60}")
    app.run(host='0.0.0.0', port=3000, debug=False, use_reloader=False)

