
document.addEventListener('DOMContentLoaded', () => {
    const chainIcon = document.getElementById('copy-link-btn');
    if (chainIcon) {
        chainIcon.addEventListener('click', () => {
            navigator.clipboard.writeText(window.location.origin).then(() => {
                const originalText = chainIcon.textContent;
                chainIcon.textContent = "✅";
                setTimeout(() => chainIcon.textContent = originalText, 1500);
            });
        });
    }
});


const searchInput = document.querySelector('.search-bar');
const searchResults = document.createElement('div');
searchResults.className = 'search-results-dropdown';
document.body.appendChild(searchResults);

let searchIndex = [];


fetch('/index.json')
    .then(response => response.json())
    .then(data => {
        searchIndex = data;
    });

searchInput.addEventListener('input', (e) => {
    const query = e.target.value.toLowerCase();
    
    if (query.length < 2) {
        searchResults.style.display = 'none';
        return;
    }

    let matches = searchIndex.filter(item => 
        item.title.toLowerCase().includes(query)
    );

    
    matches = matches.filter((item, index, self) =>
        index === self.findIndex((t) => (
            t.permalink === item.permalink
        ))
    );

    if (matches.length > 0) {
        const rect = searchInput.getBoundingClientRect();
        searchResults.style.top = `${rect.bottom + window.scrollY + 5}px`;
        searchResults.style.left = `${rect.left + window.scrollX}px`;
        searchResults.style.width = `${rect.width}px`;
        
        searchResults.innerHTML = matches.map(game => `
            <a href="${game.permalink}" class="search-result-item" style="display: flex; gap: 10px; padding: 10px; border-bottom: 1px solid #30363d; text-decoration: none; color: #c9d1d9; align-items: center; background: #24292e;">
                <img src="${game.cover}" style="width: 30px; height: 40px; object-fit: cover; border-radius: 2px;">
                <div>
                    <div style="font-weight: bold; font-size: 0.9rem;">${game.title}</div>
                    <div style="font-size: 0.75rem; color: #8b949e;">${game.rating}★ • ${game.status}</div>
                </div>
            </a>
        `).join('');
        searchResults.style.display = 'block';
    } else {
        searchResults.style.display = 'none';
    }
});


document.addEventListener('click', (e) => {
    if (!searchInput.contains(e.target) && !searchResults.contains(e.target)) {
        searchResults.style.display = 'none';
    }
});


function filterGames(status) {
    const items = document.querySelectorAll('.game-grid-item');
    const tabs = document.querySelectorAll('.filter-tab');

    
    tabs.forEach(tab => {
        if (tab.innerText === status || (status === 'All' && tab.innerText === 'All')) {
            tab.style.color = 'var(--text-main)';
            tab.style.borderBottom = '2px solid var(--accent-pink)';
        } else {
            tab.style.color = 'var(--text-muted)';
            tab.style.borderBottom = 'none';
        }
    });

    items.forEach(item => {
        if (status === 'All' || item.dataset.status === status) {
            item.style.display = 'block';
        } else {
            item.style.display = 'none';
        }
    });
}
