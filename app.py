import streamlit as st
import gpxpy
import numpy as np
import requests
from scipy.ndimage import gaussian_filter, zoom, binary_dilation
import trimesh
import tempfile
import time
import os

# --- SAYFA AYARLARI VE CSS ENJEKSİYONU ---
st.set_page_config(page_title="Toporun | 3B Koşu Haritası", page_icon="👟", layout="centered")

# Sağ üstteki varsayılan Streamlit menüsünü ve alt bilgiyi gizleyerek daha "App" gibi gösterelim
hide_st_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}
            /* Butonları biraz daha köşeli ve modern yapalım */
            .stButton>button {
                border-radius: 8px;
                font-weight: bold;
                border: 1px solid #FC4C02;
            }
            </style>
            """
st.markdown(hide_st_style, unsafe_allow_html=True)

# --- HERO SECTION (Başlık Alanı) ---
col1, col2 = st.columns([1, 4])
with col1:
    st.markdown("<h1 style='font-size: 60px; margin-bottom: 0;'>⛰️</h1>", unsafe_allow_html=True)
with col2:
    st.markdown("<h1 style='color: #FC4C02; margin-bottom: 0;'>TOPORUN</h1>", unsafe_allow_html=True)
    st.markdown("<p style='font-size: 18px; color: #A0A0A0;'>Üç Boyutlu Koşu Haritanı Oluştur</p>", unsafe_allow_html=True)

st.divider() # Estetik bir ayırıcı çizgi

st.markdown("""
**Koşu anılarını fiziksel bir sanat eserine dönüştür.**  
Strava'dan indirdiğin `.gpx` dosyasını buraya bırak, 3 boyutlu yazıcın için 
özel tasarlanmış 3B katı modelini (STL) saniyeler içinde hazırlayalım.
""")

# Fiziksel Üretim Parametreleri
FIZIKSEL_X_Y_MM = 120.0 
MAKSIMUM_Z_YUKSEKLIK_MM = 15.0 
TABAN_KALINLIGI_MM = 3.0 
ROTA_KABARTMA_MM = 3.0 

# --- DOSYA YÜKLEME VE İŞLEM ALANI ---
# Dosya yükleyiciyi estetik bir kutu (container) içine alıyoruz
with st.container():
    uploaded_file = st.file_uploader("", type=["gpx"], help="Sadece GPX formatındaki koşu verileri desteklenir.")

if uploaded_file is not None:
    st.success("✅ Veri eşleşmesi başarılı. Rotanız işlemeye hazır.")
    
    if st.button("🚀 Toporun STL Üretimini Başlat", use_container_width=True):
        
        # Eski spinner yerine çok daha modern olan ve adımları gösteren 'st.status' kullanıyoruz
        with st.status("Diorama inşa ediliyor...", expanded=True) as status:
            try:
                st.write("📍 Koordinatlar ayrıştırılıyor...")
                gpx = gpxpy.parse(uploaded_file)
                points = []
                for track in gpx.tracks:
                    for segment in track.segments:
                        for point in segment.points:
                            points.append([point.latitude, point.longitude])
                
                points = np.array(points)
                lat_min, lon_min = np.min(points, axis=0)
                lat_max, lon_max = np.max(points, axis=0)
                
                pad = 0.005 
                bbox = [lat_min-pad, lon_min-pad, lat_max+pad, lon_max+pad]

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

                st.write("⛰️ Zemin pürüzsüzleştiriliyor ve ölçekleniyor...")
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

                st.write("🏃‍♂️ Koşu rotanız yeryüzü üzerine kabartılıyor...")
                route_mask = np.zeros((target_size, target_size), dtype=bool)
                for lat, lon in points:
                    lat_ratio = (lat - bbox[0]) / (bbox[2] - bbox[0])
                    lon_ratio = (lon - bbox[1]) / (bbox[3] - bbox[1])
                    row_idx = np.clip(int(lat_ratio * (target_size - 1)), 0, target_size - 1)
                    col_idx = np.clip(int(lon_ratio * (target_size - 1)), 0, target_size - 1)
                    route_mask[row_idx, col_idx] = True

                thick_route = binary_dilation(route_mask, iterations=2)
                z_matrix_scaled[thick_route] += ROTA_KABARTMA_MM

                st.write("🧱 3B Katı Model (STL) örülüyor...")
                x = np.linspace(0, FIZIKSEL_X_Y_MM, target_size)
                y = np.linspace(0, FIZIKSEL_X_Y_MM, target_size)
                X, Y = np.meshgrid(x, y)

                vertices = []
                for i in range(target_size):
                    for j in range(target_size):
                        vertices.append([X[i, j], Y[i, j], z_matrix_scaled[i, j]])
                for i in range(target_size):
                    for j in range(target_size):
                        vertices.append([X[i, j], Y[i, j], 0.0])

                faces = []
                offset = target_size * target_size
                for i in range(target_size - 1):
                    for j in range(target_size - 1):
                        v1, v2, v3, v4 = i*target_size+j, i*target_size+j+1, (i+1)*target_size+j, (i+1)*target_size+j+1
                        faces.extend([[v1, v2, v3], [v2, v4, v3]])
                        b1, b2, b3, b4 = offset+v1, offset+v2, offset+v3, offset+v4
                        faces.extend([[b1, b3, b2], [b2, b3, b4]])

                for k in range(target_size - 1):
                    n1, n2 = k, k + 1
                    s1, s2 = (target_size-1)*target_size+k, (target_size-1)*target_size+k+1
                    faces.extend([[n1, offset+n1, n2], [n2, offset+n1, offset+n2]])
                    faces.extend([[s1, s2, offset+s1], [s2, offset+s2, offset+s1]])
                    w1, w2 = k*target_size, (k+1)*target_size
                    e1, e2 = k*target_size+target_size-1, (k+1)*target_size+target_size-1
                    faces.extend([[w1, w2, offset+w1], [w2, offset+w2, offset+w1]])
                    faces.extend([[e1, offset+e1, e2], [e2, offset+e1, offset+e2]])

                mesh = trimesh.Trimesh(vertices=vertices, faces=faces)
                mesh.fix_normals()

                with tempfile.NamedTemporaryFile(delete=False, suffix=".stl") as tmpfile:
                    mesh.export(tmpfile.name)
                    stl_path = tmpfile.name

                # Status box'ı başarıyla kapat
                status.update(label="Üretim Tamamlandı!", state="complete", expanded=False)
                
                st.balloons()
                
                # İndirme ve Sonraki Adımlar Ekranı
                st.markdown("### 🎉 Modeliniz İndirilmeye Hazır")
                
                dl_col1, dl_col2 = st.columns([1, 1])
                with dl_col1:
                    with open(stl_path, "rb") as file:
                        st.download_button(
                            label="📥 STL Dosyasını İndir",
                            data=file,
                            file_name="toporun_diorama.stl",
                            mime="model/stl",
                            use_container_width=True
                        )
                with dl_col2:
                    st.info("💡 **İpucu:** Yazıcınızın slicer programında rotanın başladığı katmana renk değişimi ekleyebilirsiniz.")
                
                os.remove(stl_path)

            except Exception as e:
                status.update(label="Üretim sırasında bir hata oluştu.", state="error")
                st.error(f"Lütfen dosyanızın geçerli bir GPX olduğundan emin olun. Detay: {e}")
