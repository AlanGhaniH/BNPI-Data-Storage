

  const logstatus = document.getElementById('log')
  const uploadForm = document.getElementById('uploadFrom')
  const shareForm = document.getElementById('shareForm')
  const fileInput = document.getElementById('fileInput');
  const fileName = document.getElementById('fileName');
  const uploadButton = document.getElementById('uploadButton');
  const downloadButton = document.getElementById('downloadSelected');
  const shareButton = document.getElementById('shareButton');
  const selectionLabel = document.getElementById('selectedDownloadLabel');
  const defaultSelectionLabel = selectionLabel?.textContent?.trim() || "Select a file to enable download.";
  const SELECTED_ENTRY_CLASSES = ["is-selected"];
  let selectedDownloadElement = null;
  let selectedDownloadCid = "";
  let selectedDownloadName = "";



  if (fileInput && fileName) {
    fileInput.addEventListener('change', () => {
      const name = fileInput.files?.[0]?.name || '';
      fileName.textContent = name || 'Choose File';
      uploadButton.disabled = false;
    });

  }

  if (uploadForm) uploadForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    fileName.textContent = 'Choose File';
    if (!fileInput || !fileInput.files || !fileInput.files[0]) {
      showLog(logstatus, JSON.stringify({ status: 'error', message: 'Please choose a file first' }));
      return;
    }
    const formData = new FormData();
    formData.append("file", fileInput.files[0]);

    const response = await fetch("/upload_file", {
      method: "POST",
      body: formData
    });

    if (!response.ok || !response.body) {
      showLog(logstatus, JSON.stringify({ status: 'error', message: 'Upload failed to start' }));
      return;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    uploadButton.disabled = true;
    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        console.log('Upload Done')
        const data = await loadBlockchainData();
        showFiles(data, 'box');
        break;
      }

      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n");
      buffer = parts.pop();

      for (const line of parts) {
        if (!line.trim()) continue;
        try {
          showLog(logstatus, line);
        } catch (err) {
          console.error("Bad JSON:", line);
        }
      }
    }

  });


  function showLog(Logbox, msg) {
            const json = JSON.parse(msg);
            const msgElement = document.createElement("p");
            msgElement.className = "whitespace-pre-wrap break-all max-w-full";
            msgElement.textContent = `[${json.status}] ${json.message}`
            Logbox.appendChild(msgElement);
  }

  function updateButtonState() {
    if (!downloadButton || !shareButton) return;
    const hasSelection = Boolean(selectedDownloadCid);
    downloadButton.disabled = !hasSelection;
    shareButton.disabled = !hasSelection;
    if (selectionLabel) {
      selectionLabel.textContent = hasSelection
        ? `Selected CID: ${selectedDownloadCid}`
        : defaultSelectionLabel;
    }
  }

  function clearSelectedDownload() {
    if (selectedDownloadElement) {
      SELECTED_ENTRY_CLASSES.forEach(cls => selectedDownloadElement.classList.remove(cls));
      selectedDownloadElement.setAttribute('aria-pressed', 'false');
    }
    selectedDownloadElement = null;
    selectedDownloadCid = "";
    selectedDownloadName = "";
    updateButtonState();
  }

  function selectDownloadCard(element) {
    if (!element || selectedDownloadElement === element) return;
    if (selectedDownloadElement) {
      SELECTED_ENTRY_CLASSES.forEach(cls => selectedDownloadElement.classList.remove(cls));
      selectedDownloadElement.setAttribute('aria-pressed', 'false');
    }
    selectedDownloadElement = element;
    selectedDownloadCid = element.dataset.cid || "";
    selectedDownloadName = element.dataset.name || "";
    SELECTED_ENTRY_CLASSES.forEach(cls => element.classList.add(cls));
    element.setAttribute('aria-pressed', 'true');
    updateButtonState();
  }

  updateButtonState();

  
async function loadBlockchainData() {
  try {
    const res = await fetch("/api/get_stored_data");
    const data = await res.json();

    return data;

    } catch (err) {
          console.error("Failed to load chat:", err);
    }
}

async function loadAddrressHistory() {
  try {
    const res = await fetch("/api/data");
    const data = await res.json();

    return data;

    } catch (err) {
          console.error("Failed to load address:", err);
    }
}

async function loadHistory(address) {
  try {
    const res = await fetch(`/api/get_send_history?address=${encodeURIComponent(address)}`);
    const data = await res.json();

    return data;

    } catch (err) {
          console.error("Failed to load address:", err);
    }
}


function showFiles(data, box) {
    const chatBox = document.getElementById(box);
    if (!chatBox) return;
    chatBox.innerHTML = ""; // Clear old messages
    clearSelectedDownload();

    const count = Array.isArray(data?.title) ? data.title.length : 0;
    for (let i = 0; i < count; i++) {
      const ts = Number(data.dt?.[i]);
      const timeString = Number.isFinite(ts)
        ? new Date(ts * 1000).toLocaleString()
        : (data.dt?.[i] || "");
      const title = data.title?.[i] || '';
      const cid = data.cid?.[i] || '';
      const meta = data.metadata?.[i] || '';

      const msgElement = document.createElement("div");
      msgElement.className = "download-options drop-button min-w-[10rem] m-5 cursor-pointer transition";
      msgElement.dataset.cid = cid;
      msgElement.dataset.name = title;
      msgElement.tabIndex = 0;
      msgElement.setAttribute("role", "button");
      msgElement.setAttribute("aria-pressed", "false");
      msgElement.innerHTML = `
              <span>${title}</span>
              <span>(${cid})</span>
              
              <div class="dropdown-content min-w-[10rem]">
                  <p><span>Meta :</span><span class="ml-4">${meta}</span></p>
                  <p>Date Uploaded :\t${timeString}</p>
              </div>
            `;
      msgElement.addEventListener("click", () => selectDownloadCard(msgElement));
      msgElement.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          selectDownloadCard(msgElement);
        }
      });
      chatBox.appendChild(msgElement);
    }


    chatBox.scrollTop = chatBox.scrollHeight;
}

async function showAddress(box) {
    try {
      const res = await fetch("/api/get_address_list");
      const data = await res.json();

      const addressDropdown = document.getElementById(box);
      addressDropdown.innerHTML = ""; // Clear old messages

    const count = Array.isArray(data?.address) ? data.address.length : 0;
    for (let i = 0; i < count; i++) {

      const msgElement = document.createElement("div");
      const address = (data.address?.[i]).slice(0, 12) + (data.address?.[i].length > 16 ? ' . . .' : '');
      
      msgElement.className = "option px-4 py-3 cursor-pointer hover:bg-[#d6dae1] transition-colors flex items-center justify-between text-gray-700";
      msgElement.setAttribute('data-value', data.address?.[i] || '');
      msgElement.innerHTML = `
                  <span>${address}</span>
                  <svg class="w-5 h-5 checkmark hidden" fill="currentColor" viewBox="0 0 20 20">
                    <path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd" />
                  </svg>
            `;
      addressDropdown.appendChild(msgElement);
    }
    } catch (err) {
      console.error("Failed to load address:", err);
    }
}

function showHistory(data, box) {

  const chatBox = document.getElementById(box);
  if (!chatBox) return;
  chatBox.innerHTML = ""; // Clear old messages

  const count = Array.isArray(data?.cid) ? data.cid.length : 0;
  for (let i = 0; i < count; i++) {
    console.log('adding box');
    const ts = Number(data.dt?.[i]);
    const timeString = Number.isFinite(ts)
        ? new Date(ts * 1000).toLocaleString()
        : (data.dt?.[i] || "");
    const cid = data.cid?.[i] || '';
    const msg = data.message?.[i] || '';
    const msgElement = document.createElement("div");

    if ((data.receiver?.[i] || '') === 'sent') {
      msgElement.className = "flex justify-end text-sm text-right";
          msgElement.innerHTML = `
              <div class="chat-box w-fit m-5">
              <span>${cid}</span><br>
              <span>${msg}</span>
              <span>(${timeString})</span>
              </div>
            `;
    } else if ((data.receiver?.[i] || '') === 'received') {
      msgElement.className = "flex justify-start text-sm text-left";
          msgElement.innerHTML = `
              <div class="chat-box w-fit m-5">
              <span>${cid}</span><br>
              <span>(${timeString})</span>
              <span>${msg}</span>
              </div>
            `;
    }
    


    chatBox.appendChild(msgElement);
  }
  chatBox.scrollTop = chatBox.scrollHeight;

}



if (downloadButton) {
  downloadButton.addEventListener("click", (event) => {
    event.preventDefault();
    if (!selectedDownloadCid) return;
    initiateDownload(selectedDownloadCid, selectedDownloadName);
  });
}



async function initiateDownload(cid, name = '') {
  if (!cid) return;
  try {
    const response = await fetch(`/download/initiate?cid=${encodeURIComponent(cid)}`);
    if (!response.ok || !response.body) return;
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n");
      buffer = parts.pop();
      for (const line of parts) {
        if (!line.trim()) continue;
        const msg = JSON.parse(line);
        if (typeof showLog === 'function') {
          try { showLog(logstatus, line); } catch (_) {}
        }
        if (msg.status === "error") {
          clearSelectedDownload();
          return;
        }
        if (msg.status === "success") {
          const url = msg.download || `/download/file?cid=${encodeURIComponent(msg.cid || cid)}&name=${encodeURIComponent(msg.name || name || '')}`;
          window.location.href = url;
          clearSelectedDownload();

        }
      }
    }
  } catch (error) {
    console.error("Download failed:", error);
  }
}

if (shareForm) shareForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  if (!selectedDownloadCid) return;

  const address = document.getElementById("addressReceiver").value;
  const message = document.getElementById("message").value;
  const cid = selectedDownloadCid;
  console.log("Sharing CID:", cid, "to address:", address, "with message:", message);
  const response = await fetch(`/share_file?address=${address}&message=${message}&cid=${cid}`);

  if (!response.ok || !response.body) {
    showLog(logstatus, JSON.stringify({ status: 'error', message: 'Fetching failed' }));
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

    
  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      console.log('Share Done')
      showAddress('dropdownMenu');
      break;
    }

    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n");
    buffer = parts.pop();

    for (const line of parts) {
      if (!line.trim()) continue;
      try {
        showLog(logstatus, line);
      } catch (err) {
        console.error("Bad JSON:", line);
      }
    }
  }

});


// Share file history 
var selectButton = document.getElementById('selectButton');
var dropdownMenu = document.getElementById('dropdownMenu');
var chevronIcon = document.getElementById('chevronIcon');
var selectedValue = document.getElementById('selectedValue');
// var options = document.querySelectorAll('.option');

selectButton.addEventListener('click', function() {
  dropdownMenu.classList.toggle('active');
  chevronIcon.classList.toggle('rotate-180');
});

dropdownMenu.addEventListener('click', async function(e) {
  const option = e.target.closest('.option'); // find closest .option
  if (!option) return; // click outside options

  const value = option.getAttribute('data-value');
  selectedValue.textContent = value.slice(0, 12) + (value.length > 16 ? ' . . .' : '');
  selectedValue.setAttribute('data-value', value);

  // Update styling + checkmarks
  dropdownMenu.querySelectorAll('.option').forEach(function(opt) {
    const checkmark = opt.querySelector('.checkmark');
    if (opt === option) {
      checkmark.classList.remove('hidden');
      opt.classList.remove('text-gray-700');
      opt.classList.add('text-gray-900');
    } else {
      checkmark.classList.add('hidden');
      opt.classList.remove('text-gray-900');
      opt.classList.add('text-gray-700');
    }
  });

  const data = await loadHistory(value);
  console.log(data);
  showHistory(data, 'history');

  dropdownMenu.classList.remove('active');
  chevronIcon.classList.remove('rotate-180');
});




document.addEventListener('click', function(e) {
  var customSelect = document.getElementById('customSelect');
  if (!customSelect.contains(e.target)) {
    dropdownMenu.classList.remove('active');
    chevronIcon.classList.remove('rotate-180');
  }
});



// Load and render on page load

(async () => {
  const data = await loadBlockchainData();
  console.log(data);
  showFiles(data, 'box');
  showAddress('dropdownMenu');
})();














