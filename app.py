import streamlit as st
import gpxpy
import numpy as np
import requests
from scipy.ndimage import gaussian_filter, zoom, binary_dilation
import trimesh
import tempfile
import time
import os
import io
import zipfile
import urllib.request
import plotly.graph_objects as go
from PIL import Image, ImageDraw, ImageFont

# --- SAYFA AYARLARI VE ULTRA-MODERN CSS ---
st.set_page_config(page_title="Toporun | Zaferini Masana Taşı", page_icon="⛰️", layout="centered")

custom_css = """
<style>
    /* Gereksiz Streamlit araçlarını gizle */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    /* Vurucu Başlıklar ve Tipografi */
    .hero-title {
        font-size: 3.5rem;
        font-weight: 900;
        text-align: center;
        color: #FFFFFF;
        margin-top: -20px;
        line-height: 1.2;
        letter-spacing: -1px;
    }
    .hero-title span { color: #FC4C02; }
    
    .hero-subtitle {
        font-size: 1.2rem;
        text-align: center;
        color: #A0A0A0;
        margin-top: 10px;
        margin-bottom: 40px;
        font-weight: 400;
    }
    
    /* Bilgi Kutucukları (Özellikler) */
    .feature-box {
        background-color: #1A1A1A;
        padding: 20px;
        border-radius: 16px;
        text-align: center;
        border: 1px solid #2A2A2A;
        transition: transform 0.3s ease, border-color 0.3s ease;
    }
    .feature-box:hover {
        transform: translateY(-5px);
        border-color: #FC4C02;
    }
    .feature-icon { font-size: 2rem; margin-bottom: 10px; }
    .feature-title { color: #FFFFFF; font-weight: bold; font-size: 1.1rem; margin-bottom: 5px; }
    .feature-desc { color: #888888; font-size: 0.9rem; }
    
    /* Buton Animasyonları */
    .stButton>button { 
        border-radius: 12px; 
        font-weight: bold; 
        font-size: 1.1rem;
        padding: 15px 30px;
        border: none; 
        color: #FFFFFF;
        background: linear-gradient(135deg, #FC4C02 0%, #D43F00 100%);
        box-shadow: 0 4px 15px rgba(252, 76, 2, 0.3);
        transition: all 0.3s ease;
    }
    .stButton>button:hover {
        transform: scale(1.02);
        box-shadow: 0 6px 20px rgba(252, 76, 2, 0.5);
    }
    
    /* Dosya Yükleme Alanı Modifikasyonu */
    [data-testid="stFileUploadDropzone"] {
        background-color: #121212 !important;
        border: 2px dashed #FC4C02 !important;
        border-radius: 16px !important;
        padding: 30px !important;
    }
</style>
"""
st.markdown(custom_css, unsafe_allow_html=True)

# --- HERO SECTION (DEVASA VİTRİN) ---
# Logoyu artık küçük bir ikon değil, devasa bir sinematik banner olarak kullanıyoruz
st.image("toporun_logo.png", use_container_width=True)

st.markdown("<div class='hero-title'>Zaferini <span>Masana Taşı</span></div>", unsafe_allow_html=True)
st.markdown("<div class='hero-subtitle'>Ter döktüğün o rotayı, çekmecede bekleyen madalyanla birleştir.<br>Sadece GPX dosyanı at, gerisini sihire bırak! 🪄</div>", unsafe_allow_html=True)

# --- 3 ADIMDA NASIL ÇALIŞIR? (Güven Veren Minimalist Kartlar) ---
c1, c2, c3 = st.columns(3)
with c1:
    st.markdown("""
    <div class='feature-box'>
        <div class='feature-icon'>📍</div>
        <div class='feature-title'>1. Rotanı Yükle</div>
        <div class='feature-desc'>Strava veya saatinden indirdiğin GPX dosyasını sürükle.</div>
    </div>
    """, unsafe_allow_html=True)
with c2:
    st.markdown("""
    <div class='feature-box'>
        <div class='feature-icon'>⚡</div>
        <div class='feature-title'>2. Önizlemeyi Gör</div>
        <div class='feature-desc'>Saniyeler içinde rotanın 3 boyutlu halini ekranda çevir.</div>
    </div>
    """, unsafe_allow_html=True)
with c3:
    st.markdown("""
    <div class='feature-box'>
        <div class='feature-icon'>🏆</div>
        <div class='feature-title'>3. Paketini Seç</div>
        <div class='feature-desc'>İster dijital indirip kendin bas, ister boyalı sipariş et.</div>
    </div>
    """, unsafe_allow_html=True)

st.write("")
st.write("")

# --- DOSYA YÜKLEME ALANI ---
uploaded_file = st.file_uploader("GPX Dosyanı Buraya Bırak", type=["gpx"])

if uploaded_file is not None:
    # Alt kısımdaki eski yeşil success bar yerine daha zarif bir mesaj
    st.info("🎯 Eşleşme başarılı! Hadi bu koşuyu ölümsüzleştirelim.")
    
    if st.button("🚀 Sihri Başlat", use_container_width=True):
# ... [Önceki kodun geri kalanı (with st.status("Diorama inşa ediliyor...") ile başlayan kısımlar) TAMAMEN AYNI KALACAK] ...
        with st.status("Diorama inşa ediliyor...", expanded=True) as status:
            try:
                st.write("📍 GPX verileri ve sporcu istatistikleri ayrıştırılıyor...")
                gpx = gpxpy.parse(uploaded_file)
                points = []
                for track in gpx.tracks:
                    for segment in track.segments:
                        for point in segment.points:
                            points.append([point.latitude, point.longitude])
                
                points = np.array(points)
                lat_min, lon_min = np.min(points, axis=0)
                lat_max, lon_max = np.max(points, axis=0)
                bbox = [lat_min-0.005, lon_min-0.005, lat_max+0.005, lon_max+0.005]

                # İstatistik Hesaplama
                moving_data = gpx.get_moving_data()
                up, down = gpx.get_uphill_downhill()
                dist_km = moving_data.moving_distance / 1000
                duration_s = moving_data.moving_time
                
                if dist_km > 0 and duration_s > 0:
                    pace_dec = (duration_s / 60) / dist_km
                    pace_min = int(pace_dec)
                    pace_sec = int((pace_dec - pace_min) * 60)
                    pace_str = f"{pace_min}:{pace_sec:02d}/km"
                    dist_str = f"{dist_km:.2f} km"
                    elev_str = f"+{int(up)}m"
                    hours, remainder = divmod(duration_s, 3600)
                    minutes, seconds = divmod(remainder, 60)
                    time_str = f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}" if hours > 0 else f"{int(minutes):02d}:{int(seconds):02d}"
                else:
                    pace_str, dist_str, elev_str, time_str = "N/A", "N/A", "N/A", "N/A"

                st.write("📡 Uzaydan topografik veriler çekiliyor...")
                grid_size = 30
                lats = np.linspace(bbox[0], bbox[2], grid_size)
                lons = np.linspace(bbox[1], bbox[3], grid_size)
                
                locations = [f"{lat},{lon}" for lat in lats for lon in lons]
                z_data_raw = []
                for i in range(0, len(locations), 100):
                    batch = "|".join(locations[i:i+100])
                    url = f"https://api.opentopodata.org/v1/srtm90m?locations={batch}"
                    try:
                        response = requests.get(url)
                        data = response.json()
                        for result in data['results']:
                            z_data_raw.append(result['elevation'] if result['elevation'] else 0)
                    except Exception:
                        z_data_raw.extend([0] * len(locations[i:i+100]))
                    time.sleep(0.5)

                st.write("⛰️ Zemin pürüzsüzleştiriliyor ve rotanız kabartılıyor...")
                z_matrix = np.array(z_data_raw).reshape((grid_size, grid_size))
                target_size = 100
                z_matrix_high_res = zoom(z_matrix, target_size / grid_size, order=3)
                z_matrix_smoothed = gaussian_filter(z_matrix_high_res, sigma=1.0)
                
                z_min, z_max = np.min(z_matrix_smoothed), np.max(z_matrix_smoothed)
                if z_max > z_min:
                    z_matrix_scaled = (z_matrix_smoothed - z_min) / (z_max - z_min) * MAKSIMUM_Z_YUKSEKLIK_MM
                else:
                    z_matrix_scaled = np.zeros_like(z_matrix_smoothed)
                z_matrix_scaled += TABAN_KALINLIGI_MM

                route_mask = np.zeros((target_size, target_size), dtype=bool)
                for lat, lon in points:
                    lat_ratio = (lat - bbox[0]) / (bbox[2] - bbox[0])
                    lon_ratio = (lon - bbox[1]) / (bbox[3] - bbox[1])
                    row_idx = np.clip(int(lat_ratio * (target_size - 1)), 0, target_size - 1)
                    col_idx = np.clip(int(lon_ratio * (target_size - 1)), 0, target_size - 1)
                    route_mask[row_idx, col_idx] = True

                thick_route = binary_dilation(route_mask, iterations=2)
                z_matrix_scaled[thick_route] += ROTA_KABARTMA_MM

                mesh = create_watertight_mesh(z_matrix_scaled, FIZIKSEL_X_Y_MM, FIZIKSEL_X_Y_MM)

                st.write("🧱 İstatistikler 3B plakaya dönüştürülüyor...")
                font_path = "Roboto-Bold.ttf"
                if not os.path.exists(font_path):
                    urllib.request.urlretrieve("https://github.com/googlefonts/roboto/raw/main/src/hinted/Roboto-Bold.ttf", font_path)
                
                plate_w, plate_h = 100.0, 30.0 
                img_w, img_h = 400, 120 
                
                image = Image.new('L', (img_w, img_h), color=0)
                draw = ImageDraw.Draw(image)
                
                text_line1 = f"MESAFE: {dist_str}   SURE: {time_str}"
                text_line2 = f"PACE: {pace_str}     YUKSEKLIK: {elev_str}"
                
                font_size = 40 
                padding = 20 
                def get_text_dims(text, fnt):
                    bbox = draw.textbbox((0, 0), text, font=fnt)
                    return bbox[2] - bbox[0], bbox[3] - bbox[1]
                
                font = ImageFont.truetype(font_path, font_size)
                w1, h1 = get_text_dims(text_line1, font)
                w2, h2 = get_text_dims(text_line2, font)
                
                while max(w1, w2) > (img_w - padding * 2) and font_size > 10:
                    font_size -= 1
                    font = ImageFont.truetype(font_path, font_size)
                    w1, h1 = get_text_dims(text_line1, font)
                    w2, h2 = get_text_dims(text_line2, font)
                
                line_spacing = font_size * 0.4
                total_h = h1 + h2 + line_spacing
                start_y = (img_h - total_h) / 2
                x1 = (img_w - w1) / 2
                x2 = (img_w - w2) / 2
                
                draw.text((x1, start_y), text_line1, font=font, fill=255)
                draw.text((x2, start_y + h1 + line_spacing), text_line2, font=font, fill=255)
                
                text_matrix = np.array(image) > 128
                text_matrix = np.flipud(text_matrix) 
                
                plate_matrix = np.full((img_h, img_w), 2.0) 
                plate_matrix[text_matrix] += 1.5 
                
                plate_mesh = create_watertight_mesh(plate_matrix, plate_w, plate_h)

                st.write("📦 Dosyalar hazırlanıyor...")
                map_bytes = mesh.export(file_type='stl')
                plate_bytes = plate_mesh.export(file_type='stl')
                
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                    zip_file.writestr("toporun_harita.stl", map_bytes)
                    zip_file.writestr("toporun_istatistik_plakasi.stl", plate_bytes)

                status.update(label="Toporun Hazır!", state="complete", expanded=False)
                
                # --- 3B İNTERAKTİF ÖNİZLEME ---
                st.markdown("### 🔍 Model Önizlemesi")
                st.caption("Farenizle 360 derece döndürerek inceleyebilirsiniz.")
                
                px, py, pz = mesh.vertices[:, 0], mesh.vertices[:, 1], mesh.vertices[:, 2]
                i_f, j_f, k_f = mesh.faces[:, 0], mesh.faces[:, 1], mesh.faces[:, 2]

                # --- ÇİFT RENKLİ MATRİS BOYAMA (VERTEX COLORING) ---
                vertex_colors = []
                for x_val, y_val, z_val in mesh.vertices:
                    # 3B uzaydaki X ve Y koordinatlarını tekrar 2D matris indekslerine çeviriyoruz
                    col_idx = np.clip(int((x_val / FIZIKSEL_X_Y_MM) * (target_size - 1)), 0, target_size - 1)
                    row_idx = np.clip(int((y_val / FIZIKSEL_X_Y_MM) * (target_size - 1)), 0, target_size - 1)
                    
                    # Nokta eğer rotanın üzerindeyse VE haritanın üst yüzeyindeyse (Z > 1.0)
                    if thick_route[row_idx, col_idx] and z_val > 1.0:
                        vertex_colors.append('#FC4C02') # Neon Strava Turuncusu
                    else:
                        vertex_colors.append('#354F2E') # Mat Topografik Yeşil

                fig = go.Figure(data=[go.Mesh3d(
                    x=px, y=py, z=pz, i=i_f, j=j_f, k=k_f,
                    vertexcolor=vertex_colors, # Tek renk ataması yerine hesaplanan dinamik dizi
                    opacity=1.0,
                    # Plastik parlamasını (specular) kısıp, pürüzlülüğü (roughness) artırarak mat bir doku elde ediyoruz
                    lighting=dict(ambient=0.4, diffuse=0.8, roughness=0.9, specular=0.1, fresnel=0.1),
                    lightposition=dict(x=100, y=100, z=100)
                )])
                
                fig.update_layout(
                    scene=dict(
                        xaxis=dict(visible=False), 
                        yaxis=dict(visible=False), 
                        zaxis=dict(visible=False), 
                        aspectratio=dict(x=1, y=1, z=0.25)
                    ),
                    margin=dict(l=0, r=0, b=0, t=0), 
                    paper_bgcolor='rgba(0,0,0,0)', 
                    plot_bgcolor='rgba(0,0,0,0)', 
                    height=450
                )
                
                st.plotly_chart(fig, use_container_width=True)
                st.divider()

                # --- YENİ E-TİCARET SATIŞ HUNİSİ (TIER CARDS) ---
                st.markdown("### 🛍️ Başarınızı Nasıl Sergilemek İstersiniz?")
                st.caption("Kendi üretim kapasitenize veya estetik beklentinize uygun paketi seçin.")
                
                # 3 Kolonlu Paket Görünümü
                c1, c2, c3 = st.columns(3)
                
                with c1:
                    with st.container():
                        st.markdown("<h3 style='text-align: center;'>💾 Dijital Paket</h3>", unsafe_allow_html=True)
                        st.markdown("<p style='text-align: center; font-size:14px; color:#A0A0A0;'>Maker Sporcular İçin</p>", unsafe_allow_html=True)
                        st.markdown("""
                        * Kendi yazıcınızda basın.
                        * STL dosyaları (Harita & Plaka).
                        * Anında Teslimat.
                        """)
                with c2:
                    with st.container():
                        st.markdown("<h3 style='text-align: center; color: #FC4C02;'>📦 Standart Paket</h3>", unsafe_allow_html=True)
                        st.markdown("<p style='text-align: center; font-size:14px; color:#A0A0A0;'>Kalite Arayanlar İçin</p>", unsafe_allow_html=True)
                        st.markdown("""
                        * Bambu Lab Kalitesinde Baskı.
                        * Antrasit şasi, neon rota.
                        * Ücretsiz Kargo.
                        """)
                with c3:
                    with st.container():
                        st.markdown("<h3 style='text-align: center;'>🎨 Premium Paket</h3>", unsafe_allow_html=True)
                        st.markdown("<p style='text-align: center; font-size:14px; color:#A0A0A0;'>Koleksiyonerler İçin</p>", unsafe_allow_html=True)
                        st.markdown("""
                        * El boyaması detaylar.
                        * Sanatsal gölgelendirme.
                        * Tam montajlı teslimat.
                        """)

                st.write("")
                paket_secimi = st.radio("Lütfen bir paket seçin:", ["Dijital Paket (Kendin Bas)", "Standart Paket (Fiziksel Ürün)", "Premium Paket (El Boyaması Eser)"], horizontal=True)

                st.divider()

                # Checkout / Teslimat Aksiyonları
                if "Dijital" in paket_secimi:
                    st.success("Tasarımınız hazır! Aşağıdaki butondan ZIP dosyanızı indirebilirsiniz.")
                    st.download_button(label="📥 Dijital Paketi İndir (ZIP)", data=zip_buffer.getvalue(), file_name="toporun_diorama_seti.zip", mime="application/zip", use_container_width=True)
                
                elif "Standart" in paket_secimi or "Premium" in paket_secimi:
                    st.info(f"Seçtiğiniz paket: **{paket_secimi}**. Üretim sürecini başlatmak için lütfen teslimat bilgilerinizi girin.")
                    with st.form("siparis_formu"):
                        form_ad = st.text_input("Ad Soyad")
                        form_tel = st.text_input("Telefon Numarası")
                        form_adres = st.text_area("Tam Kargo Adresi")
                        form_not = st.text_input("Madalya Çapınız (Örn: 65mm) - Standart ölçü için boş bırakın")
                        
                        siparis_ver = st.form_submit_button("Siparişi Tamamla", use_container_width=True)
                        
                        if siparis_ver:
                            if form_ad and form_tel and form_adres:
                                # Burada ileride bir veritabanı veya e-posta API'si (SendGrid vb.) tetiklenecek
                                st.balloons()
                                st.success(f"🎉 Teşekkürler {form_ad}! Siparişin başarıyla alındı. Üretim sürecine başlıyoruz, en kısa sürede seninle iletişime geçeceğiz.")
                            else:
                                st.error("Lütfen teslimat için ad, telefon ve adres alanlarını doldurunuz.")

            except Exception as e:
                status.update(label="Üretim sırasında bir hata oluştu.", state="error")
                st.error(f"Lütfen dosyanızın geçerli bir GPX olduğundan emin olun. Detay: {e}")
