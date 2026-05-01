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
import plotly.graph_objects as go

# --- SAYFA AYARLARI VE CSS ---
st.set_page_config(page_title="Toporun | 3B Koşu Rotanız", page_icon="👟", layout="centered")

hide_st_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}
            .stButton>button {
                border-radius: 8px;
                font-weight: bold;
                border: 1px solid #FC4C02;
            }
            </style>
            """
st.markdown(hide_st_style, unsafe_allow_html=True)

# --- HERO SECTION ---
col1, col2 = st.columns([1, 4])
with col1:
    st.image("toporun_logo.png", use_container_width=True)
with col2:
    st.markdown("<h1 style='color: #FC4C02; margin-bottom: 0;'>TOPORUN</h1>", unsafe_allow_html=True)
    st.markdown("<p style='font-size: 18px; color: #A0A0A0;'>Başarını Ölümsüzleştir</p>", unsafe_allow_html=True)

st.divider() 

# Fiziksel Parametreler
FIZIKSEL_X_Y_MM = 120.0 
MAKSIMUM_Z_YUKSEKLIK_MM = 15.0 
TABAN_KALINLIGI_MM = 3.0 
ROTA_KABARTMA_MM = 3.0 

# --- DOSYA YÜKLEME ---
with st.container():
    uploaded_file = st.file_uploader("", type=["gpx"], help="Sadece GPX formatındaki koşu verileri desteklenir.")

if uploaded_file is not None:
    st.success("✅ Veri eşleşmesi başarılı. Rotanız işlemeye hazır.")
    
    if st.button("🚀 Toporun STL Üretimini Başlat", use_container_width=True):
        
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

                # --- İSTATİSTİK HESAPLAMA (Mesafe, Süre, Pace, Yükseklik) ---
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

                st.write(f"📊 İstatistikler Çıkarıldı: {dist_str} | {time_str} | Pace: {pace_str}")

                # --- HARİTA ÜRETİMİ ---
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

                route_mask = np.zeros((target_size, target_size), dtype=bool)
                for lat, lon in points:
                    lat_ratio = (lat - bbox[0]) / (bbox[2] - bbox[0])
                    lon_ratio = (lon - bbox[1]) / (bbox[3] - bbox[1])
                    row_idx = np.clip(int(lat_ratio * (target_size - 1)), 0, target_size - 1)
                    col_idx = np.clip(int(lon_ratio * (target_size - 1)), 0, target_size - 1)
                    route_mask[row_idx, col_idx] = True

                thick_route = binary_dilation(route_mask, iterations=2)
                z_matrix_scaled[thick_route] += ROTA_KABARTMA_MM

                st.write("🧱 3B Katı Modeller (Harita ve Plaka) örülüyor...")
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

                # --- İSTATİSTİK PLAKASI ÜRETİMİ ---
                plate_w, plate_h, plate_d = 100.0, 30.0, 2.0
                plate = trimesh.creation.box(extents=[plate_w, plate_h, plate_d])
                plate.apply_translation([0, 0, plate_d/2])
                
                try:
                    import shapely
                    text_str = f"Mesafe: {dist_str}  Sure: {time_str}\nPace: {pace_str}  Yukseklik: {elev_str}"
                    text_mesh = trimesh.creation.text_3d(text_str, depth=1.5)
                    
                    # Metni plakanın ortasına hizalama ve ölçekleme
                    text_mesh.apply_translation([-text_mesh.bounds[1][0]/2, -text_mesh.bounds[1][1]/2, 0])
                    scale_factor = min((plate_w - 10) / text_mesh.extents[0], (plate_h - 10) / text_mesh.extents[1])
                    matrix = np.eye(4)
                    matrix[:3, :3] *= scale_factor
                    text_mesh.apply_transform(matrix)
                    
                    text_mesh.apply_translation([0, 0, plate_d])
                    plate_final = trimesh.util.concatenate([plate, text_mesh])
                except Exception as e:
                    plate_final = plate # Font veya kütüphane hatasında düz plaka verir

                # --- ZIP PAKETLEME SÜRECİ ---
                st.write("📦 STL dosyaları ZIP arşivine dönüştürülüyor...")
                map_bytes = mesh.export(file_type='stl')
                plate_bytes = plate_final.export(file_type='stl')
                
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                    zip_file.writestr("toporun_harita.stl", map_bytes)
                    zip_file.writestr("toporun_istatistik_plakasi.stl", plate_bytes)

                status.update(label="Üretim Tamamlandı!", state="complete", expanded=False)
                st.balloons()
                
                # --- 3B İNTERAKTİF ÖNİZLEME ---
                st.markdown("### 🔍 Model Önizlemesi")
                st.caption("Görseli farenizle döndürebilir ve yakınlaştırabilirsiniz.")
                
                px, py, pz = mesh.vertices[:, 0], mesh.vertices[:, 1], mesh.vertices[:, 2]
                i, j, k = mesh.faces[:, 0], mesh.faces[:, 1], mesh.faces[:, 2]

                fig = go.Figure(data=[go.Mesh3d(
                    x=px, y=py, z=pz, i=i, j=j, k=k,
                    color='#FC4C02', opacity=1.0,
                    lighting=dict(ambient=0.4, diffuse=0.8, roughness=0.1, specular=0.5, fresnel=0.2),
                    lightposition=dict(x=100, y=100, z=100)
                )])
                
                fig.update_layout(
                    scene=dict(
                        xaxis=dict(visible=False), yaxis=dict(visible=False), zaxis=dict(visible=False),
                        aspectratio=dict(x=1, y=1, z=0.25) 
                    ),
                    margin=dict(l=0, r=0, b=0, t=0),
                    paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', height=500
                )
                st.plotly_chart(fig, use_container_width=True)

                # --- İNDİRME EKRANI (ZIP) ---
                st.markdown("### 🎉 Üretime Hazır")
                dl_col1, dl_col2 = st.columns([1, 1])
                with dl_col1:
                    st.download_button(
                        label="📦 Toporun Setini İndir (ZIP)",
                        data=zip_buffer.getvalue(),
                        file_name="toporun_diorama_seti.zip",
                        mime="application/zip",
                        use_container_width=True
                    )
                with dl_col2:
                    st.info("💡 **Baskı İpucu:** Haritayı basarken rotanın yüksekliğinde, plakayı basarken ise metnin yüksekliğinde renk değişimi ekleyebilirsiniz.")

            except Exception as e:
                status.update(label="Üretim sırasında bir hata oluştu.", state="error")
                st.error(f"Lütfen dosyanızın geçerli bir GPX olduğundan emin olun. Detay: {e}")
