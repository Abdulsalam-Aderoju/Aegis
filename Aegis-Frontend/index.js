import { Application } from 'https://cdn.jsdelivr.net/npm/@splinetool/runtime@1.3.9/build/runtime.js';

async function initSpline() {
    const canvas = document.getElementById('canvas3d');
    if (!canvas) return;

    const app = new Application(canvas);
    try {
        // You can replace this URL with a more "health/data" themed Spline scene later
        await app.load('https://prod.spline.design/6Wq1Q7YGyM0bVzZz/scene.splinecode');
        console.log('Aegis Visual Intelligence Loaded');
    } catch (error) {
        console.error('Spline failed to load:', error);
    }
}

// Language Translation Logic
const translations = {
    en: { hero_heading: "Predicting Outbreaks, Securing Nigeria.", login_button: "Login" },
    yo: { hero_heading: "Ìsọtẹ́lẹ̀ Àjàkálẹ̀-àrùn, Ààbò Nàìjíríà.", login_button: "Wọlé" },
    ha: { hero_heading: "Hasashen Barkewar Cututtuka, Tsaron Najeriya.", login_button: "Shiga" }
};

function applyLang(lang) {
    const data = translations[lang] || translations.en;
    document.querySelectorAll('[data-i18n]').forEach(el => {
        const key = el.dataset.i18n;
        if (data[key]) el.textContent = data[key];
    });
    localStorage.setItem('aegis_lang', lang);
}

document.addEventListener('DOMContentLoaded', () => {
    initSpline();
    
    const sel = document.getElementById('lang-select');
    const saved = localStorage.getItem('aegis_lang') || 'en';
    if (sel) {
        sel.value = saved;
        sel.addEventListener('change', (e) => applyLang(e.target.value));
    }
    applyLang(saved);
});