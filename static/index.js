(() => {
  'use strict';

  const CONFIG = {
    textExtensions: ['txt', 'md', 'json', 'js', 'ts', 'jsx', 'tsx', 'css', 'scss', 'html', 'xml', 'yaml', 'yml', 'py', 'rb', 'php', 'java', 'c', 'cpp', 'h', 'go', 'rs', 'sh', 'bash', 'zsh', 'sql', 'env', 'gitignore', 'dockerfile', 'makefile', 'toml', 'ini', 'cfg', 'conf', 'log', 'csv'],
    imageExtensions: ['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'bmp', 'ico'],
    maxPanels: 4,
    autoRefreshInterval: 5000
  };

  const state = {
    auth: null,
    authStatus: 'pending',
    panels: [],
    panelIdCounter: 0,
    fileTree: null,
    pendingUploads: [],
    contextTarget: null,
    autoRefreshEnabled: true,
    autoRefreshTimer: null,
    isInitialized: false,
    selectedItems: [],
    lastSelectedItem: null,
    clipboard: { items: [], action: null },
    prefs: {
      showQuickActions: true,
      showFileSize: true,
      showExtensions: true,
      autoRefresh: true,
      backgroundAuth: true
    },
    sortBy: 'name',
    sortAsc: true,
    openMenu: null
  };

  const ICONS = {
    folder: `<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 7a2 2 0 0 1 2-2h5l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z"/></svg>`,
    file: `<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/></svg>`,
    chevron: `<span class="chevron">›</span>`,
    close: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg>`,
    refresh: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23,4 23,10 17,10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>`,
    download: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7,10 12,15 17,10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>`,
    copy: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>`,
    trash: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 6h18"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>`,
    explorer: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 7a2 2 0 0 1 2-2h5l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z"/></svg>`,
    text: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><line x1="8" y1="13" x2="16" y2="13"/><line x1="8" y1="17" x2="16" y2="17"/></svg>`,
    image: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M21 15l-5-5L5 21"/></svg>`,
    empty: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 7a2 2 0 0 1 2-2h5l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z"/><line x1="9" y1="13" x2="15" y2="13"/></svg>`,
    success: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22,4 12,14.01 9,11.01"/></svg>`,
    error: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>`,
    info: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>`,
    search: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>`
  };

  const $ = (sel, ctx = document) => ctx.querySelector(sel);
  const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];

  function getExt(filename) {
    const parts = filename.split('.');
    return parts.length > 1 ? parts.pop().toLowerCase() : '';
  }

  function formatSize(bytes) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  function isTextFile(filename) { return CONFIG.textExtensions.includes(getExt(filename)); }
  function isImageFile(filename) { return CONFIG.imageExtensions.includes(getExt(filename)); }

  function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  function getAuth() { return state.auth; }

  function setAuth(username, password) {
    state.auth = 'Basic ' + btoa(username + ':' + password);
    updateAuthStatus('pending');
    if (state.prefs.backgroundAuth) verifyAuthInBackground();
  }

  function updateAuthStatus(status) {
    state.authStatus = status;
    const indicator = $('#authIndicator');
    const statusText = $('#authStatusText');
    if (indicator) {
      indicator.classList.remove('pending', 'valid', 'invalid');
      indicator.classList.add(status);
    }
    if (statusText) {
      statusText.classList.remove('pending', 'valid', 'invalid');
      statusText.classList.add(status);
      statusText.textContent = status === 'valid' ? 'Verified' : status === 'invalid' ? 'Invalid' : 'Not verified';
    }
  }

  async function verifyAuthInBackground() {
    if (!state.auth || !state.prefs.backgroundAuth) { updateAuthStatus('pending'); return; }
    const testPath = '__auth_verify_' + Date.now() + '__';
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 5000);
      const response = await fetch('/api/files/mkdir/' + testPath, {
        method: 'POST',
        headers: { 'Authorization': state.auth },
        credentials: 'omit',
        signal: controller.signal
      });
      clearTimeout(timeoutId);
      if (response.ok) {
        fetch('/api/files/delete/' + testPath, { method: 'DELETE', headers: { 'Authorization': state.auth }, credentials: 'omit' }).catch(() => {});
        updateAuthStatus('valid');
      } else if (response.status === 401) {
        updateAuthStatus('invalid');
      } else {
        updateAuthStatus('valid');
      }
    } catch (e) {
      if (e.name !== 'AbortError') updateAuthStatus('invalid');
    }
  }

  function showAuthModal() {
    const userInput = $('#authUser');
    const passInput = $('#authPass');
    if (state.auth) {
      try {
        const decoded = atob(state.auth.replace('Basic ', ''));
        const [user] = decoded.split(':');
        userInput.value = user || '';
      } catch (e) { userInput.value = ''; }
    }
    passInput.value = '';
    openModal('authModal');
    setTimeout(() => userInput.focus(), 100);
  }

  function handleAuth() {
    const user = $('#authUser').value.trim();
    const pass = $('#authPass').value;
    if (!user || !pass) { toast('Please enter both username and password', 'error'); return; }
    setAuth(user, pass);
    closeModal('authModal');
    toast('Credentials saved', 'success');
    if (!state.isInitialized) initializeApp();
  }

  function toast(message, type = 'info') {
    const container = $('#toastContainer');
    const el = document.createElement('div');
    el.className = `toast ${type}`;
    el.innerHTML = `<span class="toast-icon">${ICONS[type] || ICONS.info}</span><span class="toast-message">${escapeHtml(message)}</span>`;
    container.appendChild(el);
    setTimeout(() => { el.classList.add('removing'); setTimeout(() => el.remove(), 200); }, 3000);
  }

  function openModal(id) { const m = $('#' + id); if (m) m.classList.add('open'); }
  function closeModal(id) { const m = $('#' + id); if (m) m.classList.remove('open'); }
  function closeAllModals() { $$('.modal.open').forEach(m => m.classList.remove('open')); }

  async function loadFileTree() {
    try {
      const fileListEl = $('#fileListData');
      if (fileListEl && fileListEl.innerHTML.trim() && !fileListEl.innerHTML.includes('FILELIST')) {
        state.fileTree = extractFileTreeFromElement(fileListEl);
        return state.fileTree;
      }
      const response = await fetch('/');
      const html = await response.text();
      const parser = new DOMParser();
      const doc = parser.parseFromString(html, 'text/html');
      const fileListInDoc = doc.querySelector('#fileListData');
      state.fileTree = fileListInDoc ? extractFileTreeFromElement(fileListInDoc) : { name: 'root', type: 'dir', children: [], path: '' };
      return state.fileTree;
    } catch (err) {
      return { name: 'root', type: 'dir', children: [], path: '' };
    }
  }

  function extractFileTreeFromElement(container) {
    const tree = { name: 'root', type: 'dir', children: [], path: '' };
    function extractRecursive(parentEl, parentNode) {
      const children = parentEl.children;
      for (let i = 0; i < children.length; i++) {
        const el = children[i];
        if (el.classList.contains('dir')) {
          const nameEl = el.querySelector('.dir-name');
          const name = nameEl ? nameEl.textContent.trim() : (el.dataset.name || 'folder');
          const node = { type: 'dir', name, path: parentNode.path ? `${parentNode.path}/${name}` : name, children: [] };
          parentNode.children.push(node);
          const nextEl = children[i + 1];
          if (nextEl && nextEl.classList.contains('children')) { extractRecursive(nextEl, node); i++; }
        } else if (el.classList.contains('file')) {
          const nameEl = el.querySelector('.file-name');
          const name = nameEl ? nameEl.textContent.trim() : (el.dataset.name || 'file');
          const path = el.dataset.path || (nameEl ? nameEl.dataset.path : null) || name;
          const sizeEl = el.querySelector('.file-size');
          const size = sizeEl ? sizeEl.textContent.trim() : '';
          parentNode.children.push({ type: 'file', name, path, size });
        } else if (el.classList.contains('children')) {
          extractRecursive(el, parentNode);
        }
      }
    }
    extractRecursive(container, tree);
    return tree;
  }

  function sortTree(node) {
    if (!node.children) return node;
    const sorted = [...node.children].sort((a, b) => {
      if (a.type !== b.type) return a.type === 'dir' ? -1 : 1;
      let cmp = 0;
      if (state.sortBy === 'name') cmp = a.name.localeCompare(b.name);
      else if (state.sortBy === 'size') cmp = (parseFloat(a.size) || 0) - (parseFloat(b.size) || 0);
      else if (state.sortBy === 'type') cmp = getExt(a.name).localeCompare(getExt(b.name));
      return state.sortAsc ? cmp : -cmp;
    });
    sorted.forEach(child => { if (child.type === 'dir') sortTree(child); });
    node.children = sorted;
    return node;
  }

  function renderFileTree(tree, searchQuery = '') {
    const query = searchQuery.toLowerCase();
    const sortedTree = sortTree(JSON.parse(JSON.stringify(tree)));
    
    function filterTree(node) {
      if (node.type === 'file') return node.name.toLowerCase().includes(query) || node.path.toLowerCase().includes(query);
      const filteredChildren = node.children.map(child => child.type === 'dir' ? filterTree(child) : (filterTree(child) ? child : null)).filter(Boolean);
      if (filteredChildren.length > 0 || node.name.toLowerCase().includes(query)) return { ...node, children: filteredChildren };
      return null;
    }

    function renderNode(node, level = 0) {
      const isCut = state.clipboard.action === 'cut' && state.clipboard.items.includes(node.path);
      const isSelected = state.selectedItems.includes(node.path);
      
      if (node.type === 'dir') {
        const hasChildren = node.children && node.children.length > 0;
        const isOpen = query || level === 0;
        let html = `<div class="tree-item dir ${isOpen ? 'open' : ''} ${isSelected ? 'selected' : ''} ${isCut ? 'cut' : ''}" data-path="${escapeHtml(node.path)}" data-name="${escapeHtml(node.name)}" data-type="dir" draggable="true">
          ${ICONS.chevron}${ICONS.folder}<span class="tree-name">${escapeHtml(node.name)}</span>
          <div class="tree-actions"><button class="tree-action action-delete" data-path="${escapeHtml(node.path)}" title="Delete">${ICONS.trash}</button></div>
        </div>`;
        if (hasChildren) {
          html += `<div class="tree-children ${isOpen ? 'open' : ''}">`;
          node.children.forEach(child => { html += renderNode(child, level + 1); });
          html += `</div>`;
        }
        return html;
      } else {
        const ext = getExt(node.name);
        return `<div class="tree-item file ${isSelected ? 'selected' : ''} ${isCut ? 'cut' : ''}" data-path="${escapeHtml(node.path)}" data-name="${escapeHtml(node.name)}" data-type="file" draggable="true">
          ${ICONS.file}<span class="tree-name">${escapeHtml(node.name)}</span>
          <div class="tree-meta">${ext ? `<span class="ext-badge" data-ext="${ext}">.${ext}</span>` : ''}<span class="file-size">${node.size || ''}</span></div>
          <div class="tree-actions">
            <button class="tree-action action-download" data-path="${escapeHtml(node.path)}" title="Download">${ICONS.download}</button>
            <button class="tree-action action-copy" data-path="${escapeHtml(node.path)}" title="Copy Link">${ICONS.copy}</button>
            <button class="tree-action action-delete" data-path="${escapeHtml(node.path)}" title="Delete">${ICONS.trash}</button>
          </div>
        </div>`;
      }
    }

    const filteredTree = query ? filterTree(sortedTree) : sortedTree;
    if (!filteredTree || filteredTree.children.length === 0) {
      return query ? `<div class="no-results">${ICONS.search}<p>No files matching "${escapeHtml(query)}"</p></div>` :
        `<div class="empty-state">${ICONS.empty}<p>No files yet</p></div>`;
    }
    let html = '';
    filteredTree.children.forEach(child => { html += renderNode(child, 0); });
    return `<div class="file-tree">${html}</div>`;
  }

  function createPanel(type, options = {}) {
    if (state.panels.length >= CONFIG.maxPanels) { toast(`Maximum ${CONFIG.maxPanels} panels`, 'info'); return null; }
    const id = `panel-${++state.panelIdCounter}`;
    const panel = { id, type, ...options };
    state.panels.push(panel);
    renderPanels();
    return panel;
  }

  function closePanel(id) {
    const idx = state.panels.findIndex(p => p.id === id);
    if (idx === -1) return;
    const panelEl = $(`#${id}`);
    if (panelEl) { panelEl.classList.add('closing'); setTimeout(() => { state.panels.splice(idx, 1); renderPanels(); }, 150); }
    else { state.panels.splice(idx, 1); renderPanels(); }
  }

  function renderPanels() {
    const workzone = $('#workzone');
    workzone.className = `panels-${Math.max(1, state.panels.length)}`;
    workzone.innerHTML = state.panels.map(panel => renderPanel(panel)).join('');
    state.panels.forEach(panel => attachPanelEvents(panel));
  }

  function renderPanel(panel) {
    let icon, title, body;
    switch (panel.type) {
      case 'explorer':
        icon = ICONS.explorer; title = 'File Explorer';
        body = renderFileTree(state.fileTree || { children: [] }, panel.searchQuery || '');
        break;
      case 'text':
        icon = ICONS.text; title = panel.path || 'Text File';
        body = `<div class="file-viewer"><div class="file-viewer-content text-viewer with-lines" id="content-${panel.id}"><div class="spinner"></div></div></div>`;
        break;
      case 'image':
        icon = ICONS.image; title = panel.path || 'Image';
        body = `<div class="file-viewer"><div class="image-viewer" id="content-${panel.id}"><div class="spinner"></div></div></div>`;
        break;
      default:
        icon = ICONS.file; title = 'Panel'; body = '<div class="empty-state"><p>Unknown</p></div>';
    }
    return `<div class="panel" id="${panel.id}" data-type="${panel.type}">
      <div class="panel-header">
        <div class="panel-title">${icon}<span>${escapeHtml(title)}</span></div>
        <div class="panel-actions">
          ${panel.type === 'explorer' ? `<button class="panel-btn btn-refresh" title="Refresh">${ICONS.refresh}</button>` : ''}
          ${panel.path ? `<button class="panel-btn btn-download" data-path="${escapeHtml(panel.path)}" title="Download">${ICONS.download}</button>` : ''}
          <button class="panel-btn btn-close" title="Close">${ICONS.close}</button>
        </div>
      </div>
      <div class="panel-body">${body}</div>
    </div>`;
  }

  function attachPanelEvents(panel) {
    const el = $(`#${panel.id}`);
    if (!el) return;
    const closeBtn = $('.btn-close', el);
    if (closeBtn) closeBtn.onclick = () => closePanel(panel.id);
    const refreshBtn = $('.btn-refresh', el);
    if (refreshBtn) refreshBtn.onclick = () => refreshExplorer(panel.id);
    const downloadBtn = $('.btn-download', el);
    if (downloadBtn) downloadBtn.onclick = () => downloadFile(panel.path);
    if (panel.type === 'text' && panel.path) loadTextFile(panel);
    else if (panel.type === 'image' && panel.path) loadImageFile(panel);
    if (panel.type === 'explorer') attachTreeEvents(el);
  }

  function getAllTreeItems() {
    const items = [];
    function traverse(node, path = '') {
      if (node.children) {
        node.children.forEach(child => {
          items.push({ path: child.path, name: child.name, type: child.type });
          if (child.type === 'dir') traverse(child, child.path);
        });
      }
    }
    if (state.fileTree) traverse(state.fileTree);
    return items;
  }

  function attachTreeEvents(container) {
    $$('.tree-item', container).forEach(item => {
      item.onclick = (e) => {
        if (e.target.closest('.tree-actions')) return;
        if (item.classList.contains('dir') && !e.shiftKey && !e.ctrlKey && !e.metaKey) {
          item.classList.toggle('open');
          const children = item.nextElementSibling;
          if (children && children.classList.contains('tree-children')) children.classList.toggle('open');
          return;
        }
        handleSelection(item, e);
      };

      item.ondblclick = (e) => {
        if (e.target.closest('.tree-actions')) return;
        const path = item.dataset.path;
        if (item.dataset.type === 'file') openFileInPanel(path);
        else {
          item.classList.add('open');
          const children = item.nextElementSibling;
          if (children && children.classList.contains('tree-children')) children.classList.add('open');
        }
      };

      item.onmousedown = (e) => {
        if (e.button === 1) {
          e.preventDefault();
          const path = item.dataset.path;
          cutItems([path]);
          toast('Cut: ' + item.dataset.name, 'info');
        }
      };

      item.oncontextmenu = (e) => {
        e.preventDefault();
        if (!state.selectedItems.includes(item.dataset.path)) {
          clearSelection();
          selectItem(item.dataset.path);
        }
        showContextMenu(e, item.dataset.path, item.dataset.type);
      };

      if (item.dataset.type === 'dir') {
        item.addEventListener('dragover', handleDragOver);
        item.addEventListener('dragleave', handleDragLeave);
        item.addEventListener('drop', handleDrop);
      }
      item.addEventListener('dragstart', handleDragStart);
      item.addEventListener('dragend', handleDragEnd);
    });

    $$('.action-download', container).forEach(btn => { btn.onclick = (e) => { e.stopPropagation(); downloadFile(btn.dataset.path); }; });
    $$('.action-copy', container).forEach(btn => { btn.onclick = (e) => { e.stopPropagation(); copyLink(btn.dataset.path); }; });
    $$('.action-delete', container).forEach(btn => { btn.onclick = (e) => { e.stopPropagation(); confirmDelete(btn.dataset.path); }; });
  }

  function handleSelection(item, e) {
    const path = item.dataset.path;
    const allItems = getAllTreeItems();
    const allPaths = allItems.map(i => i.path);

    if (e.shiftKey && state.lastSelectedItem) {
      const lastIdx = allPaths.indexOf(state.lastSelectedItem);
      const currIdx = allPaths.indexOf(path);
      if (lastIdx !== -1 && currIdx !== -1) {
        const start = Math.min(lastIdx, currIdx);
        const end = Math.max(lastIdx, currIdx);
        if (!e.ctrlKey && !e.metaKey) clearSelection();
        for (let i = start; i <= end; i++) selectItem(allPaths[i]);
      }
    } else if (e.ctrlKey || e.metaKey) {
      toggleSelection(path);
      state.lastSelectedItem = path;
    } else {
      clearSelection();
      selectItem(path);
      state.lastSelectedItem = path;
    }
    updateSelectionUI();
  }

  function selectItem(path) {
    if (!state.selectedItems.includes(path)) state.selectedItems.push(path);
    updateSelectionUI();
  }

  function toggleSelection(path) {
    const idx = state.selectedItems.indexOf(path);
    if (idx === -1) state.selectedItems.push(path);
    else state.selectedItems.splice(idx, 1);
    updateSelectionUI();
  }

  function clearSelection() {
    state.selectedItems = [];
    state.lastSelectedItem = null;
    updateSelectionUI();
  }

  function selectAll() {
    const allItems = getAllTreeItems();
    state.selectedItems = allItems.map(i => i.path);
    updateSelectionUI();
  }

  function updateSelectionUI() {
    $$('.tree-item').forEach(item => {
      item.classList.toggle('selected', state.selectedItems.includes(item.dataset.path));
    });
    const status = $('#selectionStatus');
    if (status) {
      if (state.selectedItems.length === 0) status.textContent = 'No selection';
      else if (state.selectedItems.length === 1) status.textContent = state.selectedItems[0];
      else status.textContent = `${state.selectedItems.length} items selected`;
    }
  }

  function copyItems(paths) {
    state.clipboard = { items: [...paths], action: 'copy' };
    updateClipboardUI();
    toast(`Copied ${paths.length} item(s)`, 'info');
  }

  function cutItems(paths) {
    state.clipboard = { items: [...paths], action: 'cut' };
    updateClipboardUI();
    refreshAllExplorers();
  }

  function updateClipboardUI() {
    const el = $('#clipboardStatus');
    if (el) {
      if (state.clipboard.items.length > 0) {
        el.textContent = `${state.clipboard.action === 'cut' ? '✂️' : '📋'} ${state.clipboard.items.length} item(s)`;
      } else {
        el.textContent = '';
      }
    }
  }

  async function pasteItems(destPath = '') {
    if (state.clipboard.items.length === 0) { toast('Nothing to paste', 'info'); return; }
    if (!state.auth) { toast('Set credentials first', 'error'); showAuthModal(); return; }
    
    for (const srcPath of state.clipboard.items) {
      const fileName = srcPath.split('/').pop();
      const newPath = destPath ? `${destPath}/${fileName}` : fileName;
      
      try {
        const response = await fetch(`/files/${srcPath}`);
        if (!response.ok) continue;
        const blob = await response.blob();
        const formData = new FormData();
        formData.append('file', blob);
        
        const uploadResponse = await fetch(`/api/files/upload/${newPath}`, {
          method: 'POST', headers: { 'Authorization': getAuth() }, body: formData, credentials: 'omit'
        });
        
        if (uploadResponse.status === 401) { updateAuthStatus('invalid'); toast('Invalid credentials', 'error'); return; }
        if (!uploadResponse.ok) continue;
        
        if (state.clipboard.action === 'cut') {
          await fetch(`/api/files/delete/${srcPath}`, { method: 'DELETE', headers: { 'Authorization': getAuth() }, credentials: 'omit' });
        }
        updateAuthStatus('valid');
      } catch (err) { }
    }
    
    if (state.clipboard.action === 'cut') state.clipboard = { items: [], action: null };
    updateClipboardUI();
    toast('Paste complete', 'success');
    await refreshAllExplorers();
  }

  function handleDragStart(e) {
    const path = this.dataset.path;
    if (!state.selectedItems.includes(path)) { clearSelection(); selectItem(path); }
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', state.selectedItems.join('\n'));
    this.classList.add('dragging');
  }

  function handleDragEnd(e) {
    this.classList.remove('dragging');
    $$('.tree-item.drag-over').forEach(el => el.classList.remove('drag-over'));
  }

  function handleDragOver(e) {
    e.preventDefault();
    if (this.dataset.type === 'dir') {
      this.classList.add('drag-over');
      e.dataTransfer.dropEffect = 'move';
    }
  }

  function handleDragLeave(e) { this.classList.remove('drag-over'); }

  async function handleDrop(e) {
    e.preventDefault();
    e.stopPropagation();
    this.classList.remove('drag-over');
    if (this.dataset.type !== 'dir') return;
    const targetPath = this.dataset.path;
    const items = state.selectedItems.filter(p => p !== targetPath && !targetPath.startsWith(p + '/'));
    if (items.length === 0) return;
    cutItems(items);
    await pasteItems(targetPath);
  }

  async function refreshExplorer(panelId) {
    const panel = state.panels.find(p => p.id === panelId);
    if (!panel || panel.type !== 'explorer') return;
    await loadFileTree();
    const el = $(`#${panelId} .panel-body`);
    if (el) { el.innerHTML = renderFileTree(state.fileTree, panel.searchQuery || ''); attachTreeEvents($(`#${panelId}`)); }
  }

  async function refreshAllExplorers() {
    await loadFileTree();
    state.panels.forEach(panel => {
      if (panel.type === 'explorer') {
        const el = $(`#${panel.id} .panel-body`);
        if (el) { el.innerHTML = renderFileTree(state.fileTree, panel.searchQuery || ''); attachTreeEvents($(`#${panel.id}`)); }
      }
    });
  }

  function startAutoRefresh() {
    stopAutoRefresh();
    if (state.prefs.autoRefresh) {
      state.autoRefreshTimer = setInterval(() => { if (state.isInitialized) refreshAllExplorers(); }, CONFIG.autoRefreshInterval);
    }
  }

  function stopAutoRefresh() { if (state.autoRefreshTimer) { clearInterval(state.autoRefreshTimer); state.autoRefreshTimer = null; } }

  function updateExplorerSearch(query) {
    state.panels.forEach(panel => {
      if (panel.type === 'explorer') {
        panel.searchQuery = query;
        const el = $(`#${panel.id} .panel-body`);
        if (el) { el.innerHTML = renderFileTree(state.fileTree, query); attachTreeEvents($(`#${panel.id}`)); }
      }
    });
  }

  function openFileInPanel(path) {
    if (isTextFile(path)) createPanel('text', { path });
    else if (isImageFile(path)) createPanel('image', { path });
    else downloadFile(path);
  }

  async function loadTextFile(panel) {
    const container = $(`#content-${panel.id}`);
    if (!container) return;
    try {
      const response = await fetch(`/files/${panel.path}`);
      if (!response.ok) throw new Error();
      const text = await response.text();
      const lines = text.split('\n');
      container.innerHTML = `<div class="line-numbers">${lines.map((_, i) => `<span>${i + 1}</span>`).join('')}</div><div class="code-content">${escapeHtml(text)}</div>`;
    } catch (err) { container.innerHTML = `<div class="empty-state"><p>Failed to load</p></div>`; }
  }

  function loadImageFile(panel) {
    const container = $(`#content-${panel.id}`);
    if (!container) return;
    const img = new Image();
    img.onload = () => { container.innerHTML = ''; container.appendChild(img); };
    img.onerror = () => { container.innerHTML = `<div class="empty-state"><p>Failed to load</p></div>`; };
    img.src = `/files/${panel.path}`;
  }

  function downloadFile(path) {
    const a = document.createElement('a');
    a.href = `/files/${path}`;
    a.download = path.split('/').pop();
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    toast('Download started', 'success');
  }

  function copyLink(path) {
    const url = `${location.origin}/files/${path}`;
    navigator.clipboard ? navigator.clipboard.writeText(url).then(() => toast('Link copied', 'success')).catch(() => fallbackCopy(url)) : fallbackCopy(url);
  }

  function fallbackCopy(text) {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.cssText = 'position:fixed;opacity:0;';
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    toast('Link copied', 'success');
  }

  function confirmDelete(path) {
    state.contextTarget = path;
    $('#deleteTarget').textContent = path;
    openModal('deleteModal');
  }

  async function deleteItem(path) {
    if (!state.auth) { toast('Set credentials first', 'error'); showAuthModal(); return; }
    try {
      const response = await fetch(`/api/files/delete/${path}`, { method: 'DELETE', headers: { 'Authorization': getAuth() }, credentials: 'omit' });
      if (response.status === 401) { updateAuthStatus('invalid'); toast('Invalid credentials', 'error'); return; }
      if (!response.ok) throw new Error();
      updateAuthStatus('valid');
      toast('Deleted', 'success');
      closeModal('deleteModal');
      state.selectedItems = state.selectedItems.filter(p => p !== path && !p.startsWith(path + '/'));
      await refreshAllExplorers();
    } catch (err) { toast('Delete failed', 'error'); }
  }

  async function deleteSelected() {
    if (state.selectedItems.length === 0) { toast('Nothing selected', 'info'); return; }
    if (!state.auth) { toast('Set credentials first', 'error'); showAuthModal(); return; }
    for (const path of [...state.selectedItems]) {
      try {
        const response = await fetch(`/api/files/delete/${path}`, { method: 'DELETE', headers: { 'Authorization': getAuth() }, credentials: 'omit' });
        if (response.status === 401) { updateAuthStatus('invalid'); toast('Invalid credentials', 'error'); return; }
        updateAuthStatus('valid');
      } catch (e) { }
    }
    toast('Deleted selected items', 'success');
    clearSelection();
    await refreshAllExplorers();
  }

  function showUploadModal() {
    state.pendingUploads = [];
    $('#uploadQueue').innerHTML = '';
    $('#uploadPath').value = '/';
    openModal('uploadModal');
  }

  function addFilesToUpload(files) {
    Array.from(files).forEach(file => {
      if (!state.pendingUploads.find(f => f.name === file.name)) state.pendingUploads.push(file);
    });
    renderUploadQueue();
  }

  function renderUploadQueue() {
    const queue = $('#uploadQueue');
    if (state.pendingUploads.length === 0) { queue.innerHTML = ''; queue.classList.remove('compact'); return; }
    queue.classList.toggle('compact', state.pendingUploads.length >= 4);
    queue.innerHTML = state.pendingUploads.map((file, i) => `
      <div class="upload-item" data-index="${i}">
        <div class="upload-item-icon">${ICONS.file}</div>
        <div class="upload-item-info">
          <div class="upload-item-name">${escapeHtml(file.name)}</div>
          <div class="upload-item-size">${formatSize(file.size)}</div>
          <div class="upload-item-progress"><div class="upload-item-progress-bar" style="width:0%"></div></div>
        </div>
        <button class="upload-item-remove" onclick="window.feRemoveUpload(${i})">${ICONS.close}</button>
      </div>
    `).join('');
  }

  window.feRemoveUpload = (i) => { state.pendingUploads.splice(i, 1); renderUploadQueue(); };

  async function performUpload() {
    if (state.pendingUploads.length === 0) { toast('No files', 'info'); return; }
    if (!state.auth) { toast('Set credentials first', 'error'); showAuthModal(); return; }
    let basePath = $('#uploadPath').value.trim().replace(/^\/+/, '');
    if (basePath && !basePath.endsWith('/')) basePath += '/';
    
    for (let i = 0; i < state.pendingUploads.length; i++) {
      const file = state.pendingUploads[i];
      const path = basePath + file.name;
      try {
        const formData = new FormData();
        formData.append('file', file);
        const response = await fetch(`/api/files/upload/${path}`, { method: 'POST', headers: { 'Authorization': getAuth() }, body: formData, credentials: 'omit' });
        if (response.status === 401) { updateAuthStatus('invalid'); toast('Invalid credentials', 'error'); closeModal('uploadModal'); return; }
        if (!response.ok) throw new Error();
        updateAuthStatus('valid');
        const bar = $(`.upload-item[data-index="${i}"] .upload-item-progress-bar`);
        if (bar) bar.style.width = '100%';
      } catch (err) { toast(`Failed: ${file.name}`, 'error'); }
    }
    toast('Upload complete', 'success');
    closeModal('uploadModal');
    await refreshAllExplorers();
  }

  function showFolderModal() {
    $('#folderPath').value = '';
    openModal('folderModal');
    setTimeout(() => $('#folderPath').focus(), 100);
  }

  async function createFolder() {
    const path = $('#folderPath').value.trim();
    if (!path) { toast('Enter folder path', 'error'); return; }
    if (!state.auth) { toast('Set credentials first', 'error'); showAuthModal(); return; }
    try {
      const response = await fetch(`/api/files/mkdir/${path}`, { method: 'POST', headers: { 'Authorization': getAuth() }, credentials: 'omit' });
      if (response.status === 401) { updateAuthStatus('invalid'); toast('Invalid credentials', 'error'); return; }
      if (!response.ok) throw new Error();
      updateAuthStatus('valid');
      toast('Folder created', 'success');
      closeModal('folderModal');
      await refreshAllExplorers();
    } catch (err) { toast('Failed to create folder', 'error'); }
  }

  function showContextMenu(e, path, type) {
    state.contextTarget = { path, type };
    const menu = $('#contextMenu');
    $('[data-action="open"]', menu).style.display = type === 'file' ? '' : 'none';
    $('[data-action="open-panel"]', menu).style.display = type === 'file' ? '' : 'none';
    $('[data-action="download"]', menu).style.display = type === 'file' ? '' : 'none';
    $('[data-action="paste"]', menu).style.display = type === 'dir' ? '' : 'none';
    
    const x = Math.min(e.clientX, window.innerWidth - 180);
    const y = Math.min(e.clientY, window.innerHeight - 280);
    menu.style.left = x + 'px';
    menu.style.top = y + 'px';
    menu.classList.add('open');
  }

  function hideContextMenu() { $('#contextMenu').classList.remove('open'); }

  function handleContextAction(action) {
    if (!state.contextTarget) return;
    const { path, type } = state.contextTarget;
    switch (action) {
      case 'open': openFileInPanel(path); break;
      case 'open-panel': openFileInPanel(path); break;
      case 'copy': copyItems(state.selectedItems.length > 0 ? state.selectedItems : [path]); break;
      case 'cut': cutItems(state.selectedItems.length > 0 ? state.selectedItems : [path]); break;
      case 'paste': pasteItems(path); break;
      case 'download': downloadFile(path); break;
      case 'copy-link': copyLink(path); break;
      case 'delete': confirmDelete(path); break;
    }
    hideContextMenu();
  }

  function setupMenuBar() {
    $$('.menu-item').forEach(item => {
      const label = item.querySelector('.menu-label');
      label.onclick = (e) => {
        e.stopPropagation();
        const wasOpen = item.classList.contains('open');
        closeAllMenus();
        if (!wasOpen) item.classList.add('open');
      };
      label.onmouseenter = () => {
        if (state.openMenu && state.openMenu !== item) {
          closeAllMenus();
          item.classList.add('open');
        }
      };
    });

    $$('.menu-dropdown button, .submenu-dropdown button').forEach(btn => {
      btn.onclick = (e) => {
        e.stopPropagation();
        const action = btn.dataset.action;
        if (action) handleMenuAction(action, btn);
        if (!btn.classList.contains('toggle-item') && !btn.classList.contains('submenu-trigger')) closeAllMenus();
      };
    });

    document.addEventListener('click', closeAllMenus);
  }

  function closeAllMenus() { $$('.menu-item.open').forEach(m => m.classList.remove('open')); }

  function handleMenuAction(action, btn) {
    switch (action) {
      case 'upload-file': showUploadModal(); break;
      case 'upload-folder': showUploadModal(); break;
      case 'create-folder': showFolderModal(); break;
      case 'delete-selected': deleteSelected(); break;
      case 'refresh': refreshAllExplorers(); toast('Refreshed', 'success'); break;
      case 'new-panel': createPanel('explorer'); break;
      case 'copy-selected': copyItems(state.selectedItems); break;
      case 'paste-selected': pasteItems(''); break;
      case 'cut-selected': cutItems(state.selectedItems); break;
      case 'select-all': selectAll(); break;
      case 'deselect-all': clearSelection(); break;
      case 'toggle-quick-actions':
        state.prefs.showQuickActions = !state.prefs.showQuickActions;
        btn.classList.toggle('active', state.prefs.showQuickActions);
        applyPrefs();
        break;
      case 'toggle-file-size':
        state.prefs.showFileSize = !state.prefs.showFileSize;
        btn.classList.toggle('active', state.prefs.showFileSize);
        applyPrefs();
        break;
      case 'toggle-extensions':
        state.prefs.showExtensions = !state.prefs.showExtensions;
        btn.classList.toggle('active', state.prefs.showExtensions);
        applyPrefs();
        break;
      case 'expand-all': $$('.tree-item.dir').forEach(d => { d.classList.add('open'); const c = d.nextElementSibling; if (c?.classList.contains('tree-children')) c.classList.add('open'); }); break;
      case 'collapse-all': $$('.tree-item.dir').forEach(d => { d.classList.remove('open'); const c = d.nextElementSibling; if (c?.classList.contains('tree-children')) c.classList.remove('open'); }); break;
      case 'sort-name': case 'sort-size': case 'sort-type':
        state.sortBy = action.replace('sort-', '');
        $$('[data-action^="sort-name"], [data-action^="sort-size"], [data-action^="sort-type"]').forEach(b => b.classList.toggle('active', b.dataset.action === action));
        refreshAllExplorers();
        break;
      case 'sort-asc': case 'sort-desc':
        state.sortAsc = action === 'sort-asc';
        $('[data-action="sort-asc"]').classList.toggle('active', state.sortAsc);
        $('[data-action="sort-desc"]').classList.toggle('active', !state.sortAsc);
        refreshAllExplorers();
        break;
      case 'change-credentials': showAuthModal(); break;
      case 'preferences': showPrefsModal(); break;
    }
  }

  function showPrefsModal() {
    $('#prefShowQuickActions').checked = state.prefs.showQuickActions;
    $('#prefShowFileSize').checked = state.prefs.showFileSize;
    $('#prefShowExtensions').checked = state.prefs.showExtensions;
    $('#prefAutoRefresh').checked = state.prefs.autoRefresh;
    $('#prefBackgroundAuth').checked = state.prefs.backgroundAuth;
    openModal('prefsModal');
  }

  function applyPrefs() {
    document.body.classList.toggle('show-quick-actions', state.prefs.showQuickActions);
    document.body.classList.toggle('show-file-size', state.prefs.showFileSize);
    document.body.classList.toggle('show-extensions', state.prefs.showExtensions);
    if (state.prefs.autoRefresh) startAutoRefresh();
    else stopAutoRefresh();
  }

  async function deleteEverything() {
    const user = $('#deleteAllUser').value.trim();
    const pass = $('#deleteAllPass').value;
    if (!user || !pass) { toast('Enter credentials', 'error'); return; }
    
    const testAuth = 'Basic ' + btoa(user + ':' + pass);
    if (state.auth && testAuth !== state.auth) { toast('Credentials do not match', 'error'); return; }
    
    try {
      const allItems = getAllTreeItems();
      const rootItems = allItems.filter(i => !i.path.includes('/'));
      
      for (const item of rootItems) {
        await fetch(`/api/files/delete/${item.path}`, { method: 'DELETE', headers: { 'Authorization': testAuth }, credentials: 'omit' });
      }
      
      toast('All files deleted', 'success');
      closeModal('deleteAllModal');
      closeModal('prefsModal');
      await refreshAllExplorers();
    } catch (err) { toast('Delete failed', 'error'); }
  }

  let dragCounter = 0;

  function setupGlobalDragDrop() {
    const overlay = $('#dragOverlay');
    document.addEventListener('dragenter', (e) => { if (e.dataTransfer.types.includes('Files')) { e.preventDefault(); dragCounter++; if (overlay) overlay.classList.add('active'); } });
    document.addEventListener('dragleave', (e) => { e.preventDefault(); dragCounter--; if (dragCounter === 0 && overlay) overlay.classList.remove('active'); });
    document.addEventListener('dragover', (e) => { if (e.dataTransfer.types.includes('Files')) e.preventDefault(); });
    document.addEventListener('drop', (e) => {
      if (e.dataTransfer.types.includes('Files')) {
        e.preventDefault();
        dragCounter = 0;
        if (overlay) overlay.classList.remove('active');
        if (e.dataTransfer.files.length > 0) { showUploadModal(); addFilesToUpload(e.dataTransfer.files); }
      }
    });
  }

  function setupKeyboardShortcuts() {
    document.addEventListener('keydown', (e) => {
      const tag = document.activeElement.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA') {
        if (e.key === 'Escape') { document.activeElement.blur(); closeAllModals(); hideContextMenu(); }
        return;
      }

      if (e.key === '/') { e.preventDefault(); $('#searchInput').focus(); return; }
      if (e.key === 'Escape') { clearSelection(); closeAllModals(); hideContextMenu(); closeAllMenus(); return; }
      if (e.key === 'F5') { e.preventDefault(); refreshAllExplorers(); toast('Refreshed', 'success'); return; }
      if (e.key === 'Delete') { e.preventDefault(); deleteSelected(); return; }

      if (e.ctrlKey || e.metaKey) {
        if (e.key === 'a') { e.preventDefault(); selectAll(); }
        else if (e.key === 'c') { e.preventDefault(); copyItems(state.selectedItems); }
        else if (e.key === 'x') { e.preventDefault(); cutItems(state.selectedItems); }
        else if (e.key === 'v') { e.preventDefault(); pasteItems(''); }
        else if (e.key === 'u') { e.preventDefault(); showUploadModal(); }
        else if (e.shiftKey && e.key === 'N') { e.preventDefault(); showFolderModal(); }
      }
    });
  }

  function setupEventListeners() {
    setupMenuBar();

    $('#authIndicator').onclick = () => showAuthModal();
    $('#btnConfirmAuth').onclick = handleAuth;
    $('#authPass').onkeydown = (e) => { if (e.key === 'Enter') handleAuth(); };
    $('#authUser').onkeydown = (e) => { if (e.key === 'Enter') $('#authPass').focus(); };

    const dropZone = $('#dropZone');
    const fileInput = $('#fileInput');
    dropZone.onclick = () => fileInput.click();
    fileInput.onchange = () => { if (fileInput.files.length > 0) { addFilesToUpload(fileInput.files); fileInput.value = ''; } };
    dropZone.ondragover = (e) => { e.preventDefault(); dropZone.classList.add('dragover'); };
    dropZone.ondragleave = () => dropZone.classList.remove('dragover');
    dropZone.ondrop = (e) => { e.preventDefault(); dropZone.classList.remove('dragover'); if (e.dataTransfer.files.length > 0) addFilesToUpload(e.dataTransfer.files); };

    $('#btnConfirmUpload').onclick = performUpload;
    $('#btnConfirmFolder').onclick = createFolder;
    $('#folderPath').onkeydown = (e) => { if (e.key === 'Enter') createFolder(); };
    $('#btnConfirmDelete').onclick = () => { if (state.contextTarget) deleteItem(typeof state.contextTarget === 'string' ? state.contextTarget : state.contextTarget.path); };

    $$('[data-close]').forEach(btn => { btn.onclick = () => closeAllModals(); });
    $$('.modal-backdrop').forEach(b => { b.onclick = () => closeAllModals(); });

    $$('#contextMenu button').forEach(btn => { btn.onclick = () => handleContextAction(btn.dataset.action); });
    document.addEventListener('click', (e) => { if (!e.target.closest('#contextMenu')) hideContextMenu(); });

    let searchTimeout;
    $('#searchInput').oninput = (e) => { clearTimeout(searchTimeout); searchTimeout = setTimeout(() => updateExplorerSearch(e.target.value), 200); };

    $('#prefShowQuickActions').onchange = (e) => { state.prefs.showQuickActions = e.target.checked; applyPrefs(); $('[data-action="toggle-quick-actions"]').classList.toggle('active', e.target.checked); };
    $('#prefShowFileSize').onchange = (e) => { state.prefs.showFileSize = e.target.checked; applyPrefs(); $('[data-action="toggle-file-size"]').classList.toggle('active', e.target.checked); };
    $('#prefShowExtensions').onchange = (e) => { state.prefs.showExtensions = e.target.checked; applyPrefs(); $('[data-action="toggle-extensions"]').classList.toggle('active', e.target.checked); };
    $('#prefAutoRefresh').onchange = (e) => { state.prefs.autoRefresh = e.target.checked; applyPrefs(); };
    $('#prefBackgroundAuth').onchange = (e) => { state.prefs.backgroundAuth = e.target.checked; if (e.target.checked && state.auth) verifyAuthInBackground(); };
    $('#btnChangeCredsFromPrefs').onclick = () => { closeModal('prefsModal'); showAuthModal(); };
    $('#btnDeleteEverything').onclick = () => { closeModal('prefsModal'); openModal('deleteAllModal'); };
    $('#btnConfirmDeleteAll').onclick = deleteEverything;
  }

  async function initializeApp() {
    if (state.isInitialized) return;
    applyPrefs();
    await loadFileTree();
    createPanel('explorer');
    state.isInitialized = true;
    startAutoRefresh();
  }

  function init() {
    setupEventListeners();
    setupGlobalDragDrop();
    setupKeyboardShortcuts();
    showAuthModal();
    initializeApp();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
