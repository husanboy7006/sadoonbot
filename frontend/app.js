// DIQQAT: Sayt qachonki Vercel ga yuklanganda, pastdagi manzilni o'zingizning HuggingFace serveringizga o'zgartiring!
// Misol uchun: const API_URL = "https://husanboy7006-sadoonbot.hf.space/api/mix";
const API_URL = "https://husanjon007-sadoon-api.hf.space/api/mix";

const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('image-upload');
const uploadContent = document.getElementById('upload-content');
const imagePreview = document.getElementById('image-preview');
const form = document.getElementById('mix-form');
const submitBtn = document.getElementById('submit-btn');
const btnText = document.getElementById('btn-text');
const loader = document.getElementById('loader');
const resultBox = document.getElementById('result-box');
const resultVideo = document.getElementById('result-video');
const downloadBtn = document.getElementById('download-btn');
const errorBox = document.getElementById('error-box');
const errorText = document.getElementById('error-text');

let selectedFile = null;

// Rasm tanlanganda uni ko'rsatish
function handleFile(file) {
    if (file && file.type.startsWith('image/')) {
        selectedFile = file;
        const reader = new FileReader();
        reader.onload = (e) => {
            imagePreview.src = e.target.result;
            imagePreview.style.display = 'block';
            uploadContent.style.display = 'none';
        };
        reader.readAsDataURL(file);
    }
}

// Fayl tanlash tugmasi
fileInput.addEventListener('change', (e) => {
    handleFile(e.target.files[0]);
});

// Drag and drop maxsus effektlari
dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.classList.add('dragover');
});

dropZone.addEventListener('dragleave', () => {
    dropZone.classList.remove('dragover');
});

dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
    if (e.dataTransfer.files.length) {
        handleFile(e.dataTransfer.files[0]);
    }
});

// Form yuborish, SO'ROV API'GA KETADI 
form.addEventListener('submit', async (e) => {
    e.preventDefault();

    const link = document.getElementById('insta-url').value;

    if (!selectedFile) {
        showError("Iltimos oldin rasm yuklang!");
        return;
    }

    if (!link.includes("http")) {
        showError("Havola xato kiritildi (http... bo'lishi shart).");
        return;
    }

    // Holatlarni yangilash
    errorBox.classList.add('hidden');
    resultBox.classList.add('hidden');
    submitBtn.disabled = true;
    btnText.style.display = 'none';
    loader.style.display = 'block';

    try {
        const formData = new FormData();
        formData.append("image", selectedFile);
        formData.append("url", link);

        const response = await fetch(API_URL, {
            method: 'POST',
            body: formData,
        });

        if (!response.ok) {
            throw new Error(`Server xatosi: ${response.status}`);
        }

        const data = await response.json();

        if (data.status === "success") {
            // "api/mix" o'rniga "download/..." ishlatiladi 
            const baseUrl = API_URL.replace("/api/mix", "");
            const videoUrl = baseUrl + data.download_url;
            
            // Videoni ko'rsatish va skachat tugmasini boyitish
            resultVideo.src = videoUrl;
            downloadBtn.href = videoUrl;
            resultBox.classList.remove('hidden');
            
            // Avtomatik videoni yoqishga urinish
            resultVideo.play().catch(e=>console.log(e)); 
        } else {
            showError("API Xatolik: " + data.message);
        }

    } catch (error) {
        showError(`Video qatirilishi yoki aloqada uzilish bo'ldi. Tekshiring: API ulanmagan yoki Link noto'g'ri. \nXato: ${error.message}`);
    } finally {
        submitBtn.disabled = false;
        btnText.style.display = 'block';
        loader.style.display = 'none';
        btnText.innerHTML = 'Yana yaratish <svg class="btn-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14 5l7 7m0 0l-7 7m7-7H3"></path></svg>';
    }
});

function showError(msg) {
    errorText.innerText = msg;
    errorBox.classList.remove('hidden');
}
