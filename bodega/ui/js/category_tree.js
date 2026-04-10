/**
 * CategoryTreeSelector
 * Componente reutilizable para seleccionar categorías en árbol o crear nuevas.
 */
class CategoryTreeSelector {
    constructor(containerId, options = {}) {
        this.container = document.getElementById(containerId);
        this.options = Object.assign({
            allowCreate: true,
            filterPlaceholder: "Buscar o escribir nueva...",
            onSelect: null
        }, options);

        this.categories = [];
        this.treeData = [];
        this.selectedEl = null;

        // Auto-init if not deferred
        if (!this.options.deferInit) this.Init();
    }

    async Init() {
        this.container.innerHTML = '<div class="spinner">Cargando categorías...</div>';
        await this.loadCategories();
        this.render();
    }

    setCategories(items) {
        this.categories = items || [];
        this.buildTree();
        this.render();
    }

    async loadCategories() {
        try {
            // Re-use API from window.fetchApi if available, else fetch
            const res = await window.fetchApi('/api/catalogo/categorias?include_hidden=true');
            this.categories = res.items || [];
            this.buildTree();
        } catch (e) {
            this.container.innerHTML = `<div class="error">Error al cargar categorías: ${e.message}</div>`;
        }
    }

    buildTree() {
        // Transform flat list to tree
        const map = {};
        this.categories.forEach(c => {
            map[c.id] = { ...c, children: [] };
        });

        this.treeData = [];
        this.treeData = [];
        this.categories.forEach(c => {
            if (c.parent_id && map[c.parent_id]) {
                map[c.parent_id].children.push(map[c.id]);
            } else if (!c.parent_id || c.parent_id == 0) {
                // Only strict roots (null or 0) go to top level.
                // Orphans (with parent_id but parent not found) are hidden/ignored.
                this.treeData.push(map[c.id]);
            } else {
                console.warn("Orphan category hidden from tree:", c.nombre, "Parent ID:", c.parent_id);
            }
        });
    }

    render() {
        this.container.innerHTML = '';

        // Search Bar & Toolbar
        const searchDiv = document.createElement('div');
        searchDiv.className = 'cat-tree-search';
        searchDiv.style.marginBottom = '10px';
        searchDiv.style.display = 'flex';
        searchDiv.style.borderRadius = '4px';

        // Conditional HTML based on allowCreate
        const placeholder = this.options.allowCreate ? this.options.filterPlaceholder : "Filtrar...";
        const btnHtml = this.options.allowCreate ?
            `<button id="btn-tree-create" class="btn-primary" title="Crear Categoría" style="padding:8px 12px; background:#28a745; margin-left:5px;">
                <i class="fas fa-plus"></i>
             </button>` : '';

        searchDiv.innerHTML = `
            <div style="display:flex; gap:5px; align-items:center; width:100%;">
                <input type="text" placeholder="${placeholder}" style="flex:1; padding:8px; background:rgba(255,255,255,0.05); border:1px solid #555; color:#fff; border-radius:4px;">
                ${btnHtml}
            </div>
        `;

        if (this.options.allowCreate) {
            searchDiv.innerHTML += `
                <div id="cat-desc-helper" style="font-size:0.75rem; color:#aaa; margin-top:4px;">
                    Escribe 'Padre > Hijo' para crear jerarquía.
                </div>
             `;
        }

        this.container.appendChild(searchDiv);

        const input = searchDiv.querySelector('input');
        input.addEventListener('input', (e) => this.filterTree(e.target.value));

        if (this.options.allowCreate) {
            const createBtn = searchDiv.querySelector('#btn-tree-create');
            createBtn.onclick = () => this.showCreateForm();
        }

        // Tree Container
        const treeDiv = document.createElement('div');
        treeDiv.className = 'cat-tree-nodes';
        treeDiv.style.flex = '1';
        treeDiv.style.overflowY = 'auto';
        treeDiv.style.minHeight = '150px';
        treeDiv.style.background = 'rgba(0,0,0,0.2)'; // Better contrast
        treeDiv.style.borderRadius = '4px';
        treeDiv.style.border = '1px solid rgba(255,255,255,0.05)';

        this.container.appendChild(treeDiv);
        this.treeContainer = treeDiv;

        this.renderNodes(this.treeData, this.treeContainer);
    }

    renderNodes(nodes, container, filterText = '') {
        container.innerHTML = '';
        let hasMatch = false;

        nodes.forEach(node => {
            // Filter logic
            const matchSelf = node.nombre.toLowerCase().includes(filterText.toLowerCase());

            const childContainer = document.createElement('div');
            childContainer.className = 'tree-indent';
            childContainer.style.display = 'none'; // Collapse by default

            const childHasMatch = this.renderNodes(node.children || [], childContainer, filterText);

            if (filterText && (matchSelf || childHasMatch)) {
                childContainer.style.display = 'block'; // Expand if filtering and match
            }

            if (!filterText || matchSelf || childHasMatch) {
                hasMatch = true;
                const el = document.createElement('div');
                el.className = 'tree-node';
                el.innerHTML = `<span>${node.nombre}</span>`;
                if (!node.children || node.children.length === 0) {
                    el.innerHTML += ` <i class="fas fa-tag" style="font-size:0.7rem; opacity:0.5;"></i>`;
                } else {
                    el.innerHTML = `<i class="fas fa-folder" style="font-size:0.8rem; opacity:0.7;"></i> ` + el.innerHTML;
                }

                el.onclick = (e) => {
                    e.stopPropagation();
                    // Toggle children
                    if (node.children && node.children.length > 0) {
                        childContainer.style.display = childContainer.style.display === 'none' ? 'block' : 'none';
                    }
                    // Select
                    if (this.options.onSelect) {
                        // Highlight
                        // Note: this implementation only clears highlight within THIS container recursion if simplified
                        // Prefer global clear if possible, but localized is typically ok for this component scope
                        // Let's rely on visual feedback on the element itself
                        if (this.selectedEl) this.selectedEl.classList.remove('active');
                        el.classList.add('active');
                        this.selectedEl = el;
                        this.lastSelectedNode = node; // Save for Smart Parent Suggestion

                        this.options.onSelect(node);
                    }
                };

                container.appendChild(el);
                container.appendChild(childContainer);
            }
        });

        return hasMatch;
    }

    showCreateForm() {
        // Toggle Views
        const treeDiv = this.container.querySelector('#cat-tree-view');
        const formDiv = this.container.querySelector('#cat-tree-form');
        const searchDiv = this.container.querySelector('.cat-tree-search');

        if (treeDiv) treeDiv.style.display = 'none';
        if (searchDiv) searchDiv.style.display = 'none';
        if (formDiv) {
            formDiv.style.display = 'flex';
            const nameInput = formDiv.querySelector('#cat-new-name');
            nameInput.value = ''; // Reset
            nameInput.focus();

            // Populate Parents
            const select = formDiv.querySelector('#cat-new-parent');
            select.innerHTML = '<option value="">-- Raíz (Sin Padre) --</option>';

            // Flatten categories for select, sorted by name
            const sorted = [...this.categories].sort((a, b) => (a.nombre || '').localeCompare(b.nombre || ''));
            sorted.forEach(c => {
                const opt = document.createElement('option');
                opt.value = c.id;
                opt.text = c.nombre;
                select.appendChild(opt);
            });

            // Pre-select if we have a selected node in tree
            if (this.lastSelectedNode) {
                select.value = this.lastSelectedNode.id;
            }
        }
    }

    async submitCreateCategory(name, parentId) {
        try {
            // Strategy: Use `create_category_inline` but passing [ParentName, NewName] if parent exists.
            let path = [];
            if (parentId) {
                const p = this.categories.find(c => c.id == parentId);
                if (p) path.push(p.nombre);
            }
            path.push(name);

            await window.fetchApi('/api/catalogo/categorias/inline', {
                method: 'POST',
                body: { path: path }
            });

            alert("Categoría creada");

            // Reload and Restore View
            await this.loadCategories();

            // Hacky restore view
            const treeDiv = this.container.querySelector('#cat-tree-view');
            const formDiv = this.container.querySelector('#cat-tree-form');
            const searchDiv = this.container.querySelector('.cat-tree-search');
            if (formDiv) formDiv.style.display = 'none';
            if (treeDiv) treeDiv.style.display = 'block';
            if (searchDiv) searchDiv.style.display = 'block';

        } catch (e) {
            alert("Error: " + e.message);
        }
    }

    filterTree(text) {
        this.renderNodes(this.treeData, this.treeContainer, text);
    }

    showCreateForm() {
        const modal = document.getElementById('modal-create-category');
        if (!modal) return alert("Modal de creación no encontrado en HTML");

        const nameInput = document.getElementById('modal-cat-name');

        // Parent Picker logic (Tree-based)
        const parentNameInput = document.getElementById('modal-cat-parent-name');
        const parentIdInput = document.getElementById('modal-cat-parent-id');

        // Reset Inputs
        nameInput.value = '';
        parentIdInput.value = '';
        parentNameInput.value = '-- Raíz (Sin Padre) --';

        // Initialize Picker Tree if needed
        if (!window.parentPickerTree) {
            window.parentPickerTree = new window.CategoryTreeSelector('modal-parent-tree-container', {
                allowCreate: false, // Read-only selection mode
                deferInit: true, // Wait for manual data set
                onSelect: (node) => {
                    document.getElementById('modal-cat-parent-id').value = node.id;
                    document.getElementById('modal-cat-parent-name').value = node.nombre;
                }
            });
        }
        // Sync Data (avoid re-fetch)
        window.parentPickerTree.setCategories(this.categories);

        // Pre-select if we have a selected node in main tree
        if (this.lastSelectedNode) {
            // Can we programmatically select in the picker?
            // For now just set the value inputs, visual selection in tree might require extra logic.
            // Let's settle for setting value.
            parentIdInput.value = this.lastSelectedNode.id;
            parentNameInput.value = this.lastSelectedNode.nombre;
        }

        let saveBtn = document.getElementById('btn-modal-create-save');
        // Unbind previous onclick to avoid duplicates
        const newBtn = saveBtn.cloneNode(true);
        saveBtn.parentNode.replaceChild(newBtn, saveBtn);
        saveBtn = newBtn; // Update reference to the new button

        saveBtn.onclick = async () => {
            const name = nameInput.value.trim();
            const parentId = parentIdInput.value;
            if (!name) return alert("Ingresa un nombre");

            await this.submitCreateCategory(name, parentId);
            modal.close();
        };

        modal.showModal();
    }

    async submitCreateCategory(name, parentId) {
        try {
            // Build path for inline creator or use separate logic
            // Since backend "create_category_inline" expects PATH List.
            // We reconstruct path from Parent
            let path = [];
            if (parentId) {
                // Find parent recursive? No, flat list is in this.categories
                const p = this.categories.find(c => c.id == parentId);
                // Problem: create_category_inline needs FULL path (Grandparent > Parent > Child).
                // If we only give [Parent, Child] it acts relative? No, it searches from root.
                // WE NEED FULL PATH.
                // We should traverse up parents.

                // Helper to build path up
                let curr = p;
                while (curr) {
                    path.unshift(curr.nombre);
                    if (curr.parent_id) {
                        curr = this.categories.find(c => c.id == curr.parent_id);
                    } else {
                        curr = null;
                    }
                }
            }
            path.push(name);

            await window.fetchApi('/api/catalogo/categorias/inline', {
                method: 'POST',
                body: { path: path }
            });

            alert("Categoría creada");
            await this.loadCategories(); // Reload tree
        } catch (e) {
            alert("Error: " + e.message);
        }
    }
}
window.CategoryTreeSelector = CategoryTreeSelector;
