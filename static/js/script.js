// MADA — interactions front-end légères (aucune dépendance)
window.mada = {
    /**
     * Met à jour la liste des catégories du formulaire d'opération
     * selon le type sélectionné (recette / dépense).
     */
    updateCategories(form) {
        const type = form.querySelector('input[name="type"]:checked').value;
        const select = document.getElementById('categorie-select');
        if (!select) return;

        const options = type === 'recette' ? window.CATEGORIES_RECETTE : window.CATEGORIES_DEPENSE;
        select.innerHTML = '';
        options.forEach((cat) => {
            const opt = document.createElement('option');
            opt.value = cat;
            opt.textContent = cat;
            select.appendChild(opt);
        });
    },
};

// Rendre les catégories accessibles globalement si définies inline dans le template
document.addEventListener('DOMContentLoaded', () => {
    if (typeof CATEGORIES_RECETTE !== 'undefined') {
        window.CATEGORIES_RECETTE = CATEGORIES_RECETTE;
        window.CATEGORIES_DEPENSE = CATEGORIES_DEPENSE;
    }

    // Fermeture automatique des messages flash après 5s
    document.querySelectorAll('.flash').forEach((el) => {
        setTimeout(() => {
            el.style.transition = 'opacity 0.4s ease';
            el.style.opacity = '0';
            setTimeout(() => el.remove(), 400);
        }, 5000);
    });
});
