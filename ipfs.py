import json
import os
import shutil
import tarfile
from typing import Any, Dict, List, Optional
import time
from dotenv import load_dotenv
import requests

load_dotenv()
DEFAULT_API_URL = os.getenv("IPFS_API_URL", "http://127.0.0.1:5001/api/v0") # local by default
try:
    DEFAULT_TIMEOUT = None
except ValueError:
    DEFAULT_TIMEOUT = None


def _build_url(base_url: str, endpoint: str) -> str:
    base = base_url.rstrip("/")
    path = endpoint.lstrip("/")
    return f"{base}/{path}"


def _resolve_remote_base(pinning_node: str, pinning_access: str) -> str:
    """Map the legacy pinning args to an HTTP base URL."""
    if pinning_node.startswith(("http://", "https://")):
        url = pinning_node.rstrip("/")
        if url.endswith("/api/v0"):
            url = url[: -len("/api/v0")]
        return f"{url}/api/v0"
    scheme = "https" if pinning_access.lower() == "https" else "http"
    host = pinning_node
    if ":" not in host:
        host = f"{host}:5001"
    return f"{scheme}://{host}/api/v0"

def cluster_test(cluster_node: str):
    try:
        id = requests.get(f"http://{cluster_node}:9094/id").json()
        print(f"\n--- Cluster Peers for {id['id']} ---")
        return True
    except Exception as e:
        print(f"[FAIL] peers check error {cluster_node} → {e}")
        return False


def upload_to_ipfs(
    file_loc: str,
    api_url: str = DEFAULT_API_URL,
    wrap_with_directory: bool = True,
) -> Optional[str]:
    """
    Upload a file to IPFS using the HTTP API and return the resulting CID.

    :param file_loc: Path to the file to be uploaded.
    :param api_url: Base URL for the IPFS HTTP API.
    :param wrap_with_directory: Wrap the file in a virtual directory (produces a stable root CID).
    :return: CID string on success, None otherwise.
    """
    if not os.path.isfile(file_loc):
        print(f"File not found: {file_loc}")
        return None

    try:
        with open(file_loc, "rb") as handle:
            files = {"file": (os.path.basename(file_loc), handle)}
            params = {"wrap-with-directory": "true" if wrap_with_directory else None,
            "pin": "false",
            }
            response = requests.post(
                _build_url(api_url, "add"),
                files=files,
                params=params,
                stream=True,
            )
        try:
            response.raise_for_status()
            entries: List[Dict[str, Any]] = []
            for line in response.iter_lines(decode_unicode=True):
                if not line:
                    continue
                entries.append(json.loads(line))
            if not entries:
                return None
            return entries[-1].get("Hash")
        finally:
            response.close()
    except (OSError, requests.RequestException, json.JSONDecodeError) as error:
        print(f"An error occurred: {error}")
        return None


def pin_to_ipfs(
    cid: str,
    pinning_node: str,
    pinning_access: str = "ip4",
) -> Optional[Dict[str, Any]]:
    """
    Pin a CID on a remote IPFS node exposed through the HTTP API.

    :param cid: The CID to pin.
    :param pinning_node: Hostname, IP, or base URL of the pinning service.
    :param pinning_access: Legacy protocol hint; use "https" to force HTTPS.
    :return: Parsed JSON response on success, None otherwise.
    """
    base_url = _resolve_remote_base(pinning_node, pinning_access)

    try:
        response = requests.post(
            _build_url(base_url, "pin/add"),
            params={"arg": cid},
            timeout=DEFAULT_TIMEOUT,
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as error:
        print(f"An error occurred: {error}")
        return None

def pin_to_ipfs_cluster(
    cid: str,
    pinning_node: str,
    require_all_peers: bool = False,
    POLL_INTERVAL: int = 1,
) -> Optional[Dict[str, Any]]:
    """
    Pin a CID on an IPFS Cluster node and wait indefinitely until:
      • ANY peer becomes 'pinned'          (default)
      • ALL peers become 'pinned'          (if require_all_peers=True)
      • ANY peer becomes 'pin_error'       → exit early

    No timeout. Infinite loop for testing environments.
    """

    base_url = f"http://{pinning_node}:9094"

    # --- 1) Send pin request ---
    try:
        pin_resp = requests.post(
            _build_url(base_url, f"pins/{cid}"),
        )
        pin_resp.raise_for_status()
    except requests.RequestException as error:
        print(f"[pin_to_cluster_and_wait] Pin request failed: {error}")
        return None

    # --- 2) Infinite polling ---
    print(f"[pin_to_cluster_and_wait] Pin submitted. Waiting for cluster...")

    while True:
        try:
            st_resp = requests.get(_build_url(base_url, f"pins/{cid}"))
            st_resp.raise_for_status()
            status_json = st_resp.json()
        except requests.RequestException as error:
            print(f"[pin_to_cluster_and_wait] Status check failed: {error}")
            time.sleep(POLL_INTERVAL)
            continue

        peer_map = status_json.get("peer_map", {}) or {}

        if not peer_map:
            print("[wait] No peer_map yet… waiting…")
            time.sleep(POLL_INTERVAL)
            continue

        # Extract statuses
        peer_statuses = {peer: data.get("status") for peer, data in peer_map.items()}

        print(f"[wait] statuses: {peer_statuses}")

        # --- ERROR HANDLING ---
        #if "pin_error" in peer_statuses.values() and not "pinned" in peer_statuses.values():
        #    print("[ERROR] One peer returned pin_error. Exiting.")
        #    return peer_statuses

        # --- SUCCESS CONDITIONS ---
        if not require_all_peers and "pinned" in peer_statuses.values():
            print("[SUCCESS] A peer has pinned the CID!")
            return peer_statuses

        if require_all_peers and all(s == "pinned" for s in peer_statuses.values()):
            print("[SUCCESS] All peers have pinned the CID!")
            return peer_statuses
        if all(s == "pin_error" for s in peer_statuses.values()):
            print("[ERROR] all peer returned pin_error. Exiting.")
            return peer_statuses

        time.sleep(POLL_INTERVAL)

def garbage_collect_ipfs(api_url: str = DEFAULT_API_URL) -> Optional[List[Dict[str, Any]]]:
    """
    Trigger garbage collection on the local IPFS node.

    :param api_url: Base URL for the IPFS HTTP API.
    :return: List of GC results on success, None otherwise.
    """
    try:
        response = requests.post(
            _build_url(api_url, "repo/gc"),
            stream=True,
        )
        response.raise_for_status()
        items: List[Dict[str, Any]] = []
        for line in response.iter_lines():
            if not line:
                continue
            items.append(json.loads(line.decode("utf-8")))
        return items
    except requests.RequestException as error:
        print(f"An error occurred: {error}")
        return None


def download_from_ipfs(
    cid: str,
    output_dir: str,
    filename: Optional[str] = None,
    api_url: str = DEFAULT_API_URL,
) -> Optional[str]:
    """
    Download a CID from IPFS and write the payload to disk.

    :param cid: The CID to download (file CID or root CID when combined with filename).
    :param output_dir: Base directory where the file tree will be created.
    :param filename: Optional explicit file name when using root CID directories.
    :param api_url: Base URL for the IPFS HTTP API.
    :return: Absolute path to the downloaded file on success, None otherwise.
    """
    root_cid = cid.strip("/").split("/")[0]
    if not root_cid:
        print("Invalid CID supplied")
        return None

    path_suffix = ""
    if "/" in cid.strip("/"):
        path_suffix = "/".join(cid.strip("/").split("/")[1:])
    if filename:
        path_suffix = filename.lstrip("/")

    def _cat(target: str) -> requests.Response:
        return requests.post(
            _build_url(api_url, "cat"),
            params={"arg": target},
            stream=True,
        )

    target_cid = root_cid if not path_suffix else f"{root_cid}/{path_suffix}"
    response: Optional[requests.Response] = None
    try:
        response = _cat(target_cid)
        try:
            response.raise_for_status()
        except requests.HTTPError as http_err:
            is_directory = (
                response.status_code == 500
                and path_suffix == ""
                and "this dag node is a directory" in response.text.lower()
            )
            response.close()
            if not is_directory:
                raise http_err
            # fetch ipfs rpc api to list files under the directory
            listing = requests.post(
                _build_url(api_url, "ls"),
                params={"arg": root_cid},
                timeout=DEFAULT_TIMEOUT,
            )
            listing.raise_for_status()
            listing_payload = listing.json()
            objects = listing_payload.get("Objects") or []
            links = objects[0].get("Links") if objects else []


            if not links:
                print(f"No files found under CID {root_cid}")
                return None
            path_suffix = links[0].get("Name") or ""
            if not path_suffix:
                print(f"Unable to determine file name for CID {root_cid}")
                return None



            target_cid = f"{root_cid}/{path_suffix}"
            response = _cat(target_cid)
            response.raise_for_status()

        root_dir = os.path.join(output_dir, root_cid)
        os.makedirs(root_dir, exist_ok=True)

        target_name = filename or (path_suffix.split("/")[-1] if path_suffix else root_cid)
        if not target_name:
            target_name = "file"
        target_path = os.path.join(root_dir, target_name)

        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        with open(target_path, "wb") as handle:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    handle.write(chunk)
        return os.path.abspath(target_path)
    except (OSError, requests.RequestException, json.JSONDecodeError) as error:
        print(f"An error occurred: {error}")
        return None
    finally:
        if response is not None:
            response.close()


def get_from_ipfs(
    cid: str,
    output_dir: str,
    api_url: str = DEFAULT_API_URL,
) -> bool:
    """
    Fetch an IPFS object using /api/v0/get and unpack the returned TAR archive.

    :param cid: Root CID or CID/path to retrieve.
    :param output_dir: Directory where the extracted content will be stored.
    :param api_url: Base URL for the IPFS HTTP API.
    :return: True if extraction succeeds, False otherwise.
    """
    root_cid = cid.strip("/").split("/")[0]
    if not root_cid:
        print("Invalid CID supplied")
        return False

    base_dir = os.path.join(output_dir, root_cid)
    base_abs = os.path.abspath(base_dir)

    response: Optional[requests.Response] = None
    try:
        response = requests.post(
            _build_url(api_url, "get"),
            params={
                "arg": cid,
                "archive": "true",
            },
            stream=True,
            )
        response.raise_for_status()

        os.makedirs(base_dir, exist_ok=True)
        response.raw.decode_content = True

        extracted_any = False
        with tarfile.open(fileobj=response.raw, mode="r|*") as bundle:
            for member in bundle:
                name = member.name.lstrip("./")
                if not name:
                    continue

                target_path = os.path.abspath(os.path.join(base_abs, name))
                if not target_path.startswith(base_abs):
                    print(f"Skipping unsafe member path: {member.name}")
                    continue

                if member.isdir():
                    os.makedirs(target_path, exist_ok=True)
                    continue

                source = bundle.extractfile(member)
                if source is None:
                    continue

                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                with source, open(target_path, "wb") as handle:
                    shutil.copyfileobj(source, handle)
                extracted_any = True

        if not extracted_any:
            print(f"No files extracted for CID {cid}")
        return extracted_any
    except (requests.RequestException, tarfile.TarError, OSError) as error:
        print(f"An error occurred: {error}")
        return False
    finally:
        if response is not None:
            response.close()
# Test
import argparse

def test():



    # os.makedirs('ipfs_up', exist_ok=True)
    os.makedirs('ipfs_down', exist_ok=True)
    sample_path = "contracts\\contract_info.json"
    cid = upload_to_ipfs(sample_path)
    print(f"file cid: {cid}")
    saved_path = download_from_ipfs(cid, "ipfs_down")
    print(f"download path: {saved_path}")
    get_from_ipfs(cid, "ipfs_down")


if __name__ == "__main__":
    test()