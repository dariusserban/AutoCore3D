const app = document.getElementById('app');
const products = [
    { id: 1, name: "Admisie BMW M57", price: 450, mat: "ASA-CF", img: "https://via.placeholder.com/300/1a1a1a/ff6700?text=AutoCore3D" },
    { id: 2, name: "Suport Proiectoare Eclipse", price: 180, mat: "ABS+", img: "https://via.placeholder.com/300/1a1a1a/ff6700?text=AutoCore3D" }
];

app.innerHTML = `
    <nav class="p-6 border-b border-white/10 flex justify-between items-center">
        <h1 class="text-2xl font-bold text-[#FF6700]">AUTOCORE3D</h1>
        <span class="text-xs bg-white/10 px-2 py-1">3D PRINTING & ENGINEERING</span>
    </nav>
    <div class="p-8 grid grid-cols-1 md:grid-cols-2 gap-6">
        ${products.map(p => `
            <div class="glass-card p-6 rounded-lg">
                <img src="${p.img}" class="w-full mb-4 rounded">
                <h3 class="text-xl font-bold">${p.name}</h3>
                <p class="text-[#FF6700] mb-4">${p.mat}</p>
                <div class="flex justify-between items-center">
                    <span class="text-2xl font-bold">${p.price} RON</span>
                    <button class="bg-[#FF6700] text-black px-4 py-2 font-bold text-xs uppercase">Detalii WhatsApp</button>
                </div>
            </div>
        `).join('')}
    </div>
`;