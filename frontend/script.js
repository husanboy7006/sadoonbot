document.addEventListener('DOMContentLoaded', () => {
    // ---------------------------------------------------------
    // TABLARNI BOSHQARISH
    // ---------------------------------------------------------
    const tabBtns = document.querySelectorAll('.tab-btn');
    const tabContents = document.querySelectorAll('.tab-content');

    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const tabId = btn.getAttribute('data-tab');

            // Aktiv tugmani o'zgartirish
            tabBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            // Aktiv bo'limni o'zgartirish
            tabContents.forEach(c => c.classList.remove('active'));
            document.getElementById(`${tabId}Tab`).classList.add('active');

            // Natijalarni tozalash (tab o'zgarganda)
            document.getElementById('resultArea').classList.add('hidden');
        });
    });

    // ---------------------------------------------------------
    // KERAKLI ELEMENTLAR
    // ---------------------------------------------------------
    const API_BASE = 'http://127.0.0.1:8000/api';
    const loader = document.getElementById('loader');
    const resultArea = document.getElementById('resultArea');
    const videoResult = document.getElementById('videoResult');
    const shazamResult = document.getElementById('shazamResult');
    const outputVideo = document.getElementById('outputVideo');
    const downloadBtn = document.getElementById('downloadBtn');

    // ---------------------------------------------------------
    // 1. MIX - VIDEO YASASH
    // ---------------------------------------------------------
    const mixBtn = document.getElementById('mixBtn');
    mixBtn.addEventListener('click', async () => {
        const file = document.getElementById('imageInput').files[0];
        const url = document.getElementById('mixUrl').value;

        if (!file || !url) return alert('Rasm va linkni kiriting! 📸🔗');

        showLoading(true);
        const fd = new FormData();
        fd.append('image', file);
        fd.append('url', url);

        try {
            const res = await fetch(`${API_BASE}/mix`, { method: 'POST', body: fd });
            const data = await res.json();
            if (data.status === 'success') {
                showVideoResult(data.download_url);
            } else alert(data.message);
        } catch (e) { alert('Server bilan aloqa uzildi! 🛠️'); }
        showLoading(false);
    });

    // ---------------------------------------------------------
    // 2. SHAZAM - MUSIQANI TOPISH
    // ---------------------------------------------------------
    const shazamBtn = document.getElementById('shazamBtn');
    shazamBtn.addEventListener('click', async () => {
        const file = document.getElementById('shazamFile').files[0];
        const url = document.getElementById('shazamUrl').value;

        if (!file && !url) return alert('Link yuboring yoki fayl tanlang! 🎵');

        showLoading(true);
        const fd = new FormData();
        if (file) fd.append('file', file);
        if (url) fd.append('url', url);

        try {
            const res = await fetch(`${API_BASE}/shazam`, { method: 'POST', body: fd });
            const data = await res.json();
            if (data.status === 'success') {
                showShazamResult(data.track);
            } else alert(data.message);
        } catch (e) { alert('Server bilan aloqa uzildi! 🛠️'); }
        showLoading(false);
    });

    // ---------------------------------------------------------
    // 3. DOWNLOADER - VIDEONI YUKLASH
    // ---------------------------------------------------------
    const downBtn = document.getElementById('downBtn');
    downBtn.addEventListener('click', async () => {
        const url = document.getElementById('downUrl').value;
        if (!url) return alert('Linkni kiriting! 🔗');

        showLoading(true);
        const fd = new FormData();
        fd.append('url', url);

        try {
            const res = await fetch(`${API_BASE}/download-video`, { method: 'POST', body: fd });
            const data = await res.json();
            if (data.status === 'success') {
                showVideoResult(data.download_url);
            } else alert(data.message);
        } catch (e) { alert('Server bilan aloqa uzildi! 🛠️'); }
        showLoading(false);
    });

    // ---------------------------------------------------------
    // YORDAMCHI FUNKSIYALAR
    // ---------------------------------------------------------
    function showLoading(show) {
        loader.style.display = show ? 'block' : 'none';
        if (show) resultArea.classList.add('hidden');
    }

    function showVideoResult(downloadUrl) {
        resultArea.classList.remove('hidden');
        videoResult.classList.remove('hidden');
        shazamResult.classList.add('hidden');
        const fullUrl = `http://127.0.0.1:8000${downloadUrl}`;
        outputVideo.src = fullUrl;
        downloadBtn.href = fullUrl;
    }

    function showShazamResult(track) {
        resultArea.classList.remove('hidden');
        videoResult.classList.add('hidden');
        shazamResult.classList.remove('hidden');

        document.getElementById('trackImg').src = track.image || 'https://via.placeholder.com/150';
        document.getElementById('trackTitle').innerText = track.title;
        document.getElementById('trackArtist').innerText = track.subtitle;
        document.getElementById('shazamLink').href = track.shazam_url;
    }
});
