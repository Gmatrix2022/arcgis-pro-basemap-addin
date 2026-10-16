#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ArcGIS Pro Basemap Add-In — Stage-0 & Microservice End-to-End Verification Suite (G1–G6)
自动化验证 MapsforgeTileServer 的六大工程门禁，并输出量化 JSON 报告与多图层合成视觉样片。
"""
import io
import json
import math
import os
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import urllib.error
from pathlib import Path
from PIL import Image, ImageDraw

WORKSPACE_ROOT = Path(r"d:\AIAssistant\GeoAI地理空间地图创作智能体")
PROJ_ROOT = WORKSPACE_ROOT / "projects" / "arcgis-pro-basemap-addin"
SERVER_DIR = PROJ_ROOT / "bin" / "Server"
THEMES_DIR = PROJ_ROOT / "themes"
OUT_REPORT_DIR = PROJ_ROOT / "tests" / "results"

JAVA_EXE = r"C:\Program Files\Java\jdk-17\bin\java.exe"
PORT = 18765
BASE_URL = f"http://127.0.0.1:{PORT}"

MAP_YUNNAN_OFFICIAL = WORKSPACE_ROOT / "data" / "_inbox" / "yunnan.map"
MAP_YUNNAN_OAM = WORKSPACE_ROOT / "data" / "_inbox" / "Ch-Yunnan_oam.osm.map"
MAP_N24E102 = WORKSPACE_ROOT / "data" / "_inbox" / "locus" / "mapsVector" / "N24E102.map"
MAP_N25E102 = WORKSPACE_ROOT / "data" / "_inbox" / "locus" / "mapsVector" / "N25E102.map"
MAP_N27E100 = WORKSPACE_ROOT / "data" / "_inbox" / "locus" / "mapsVector" / "N27E100.map"


def latlon_to_xyz(lat: float, lon: float, z: int):
    n = 2 ** z
    x = int((lon + 180.0) / 360.0 * n)
    lat_rad = math.radians(lat)
    y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return x, y


def http_get_json(path: str):
    req = urllib.request.Request(f"{BASE_URL}{path}")
    with urllib.request.urlopen(req, timeout=15) as resp:
        hdrs = {k.lower(): v for k, v in resp.headers.items()}
        return resp.status, hdrs, json.loads(resp.read().decode("utf-8"))


def http_post_form(path: str, data: dict):
    encoded = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(f"{BASE_URL}{path}", data=encoded, method="POST")
    with urllib.request.urlopen(req, timeout=20) as resp:
        hdrs = {k.lower(): v for k, v in resp.headers.items()}
        return resp.status, hdrs, json.loads(resp.read().decode("utf-8"))


def http_get_bytes(path: str):
    req = urllib.request.Request(f"{BASE_URL}{path}")
    with urllib.request.urlopen(req, timeout=20) as resp:
        hdrs = {k.lower(): v for k, v in resp.headers.items()}
        return resp.status, hdrs, resp.read()


def analyze_png(png_bytes: bytes):
    img = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    w, h = img.size
    pixels = list(img.getdata())
    total = len(pixels)
    transparent_cnt = sum(1 for r, g, b, a in pixels if a == 0)
    visible_cnt = total - transparent_cnt
    # Count visible pixels in top half vs bottom half
    top_visible = sum(1 for idx, (r, g, b, a) in enumerate(pixels) if (idx // w) < (h // 2) and a > 0)
    bot_visible = sum(1 for idx, (r, g, b, a) in enumerate(pixels) if (idx // w) >= (h // 2) and a > 0)
    return {
        "width": w,
        "height": h,
        "mode": img.mode,
        "total_pixels": total,
        "transparent_pixels": transparent_cnt,
        "visible_pixels": visible_cnt,
        "transparent_ratio": round(transparent_cnt / total, 4),
        "visible_ratio": round(visible_cnt / total, 4),
        "top_half_visible": top_visible,
        "bottom_half_visible": bot_visible,
        "image": img,
    }


def main():
    OUT_REPORT_DIR.mkdir(parents=True, exist_ok=True)
    server_themes_dir = SERVER_DIR / "themes"
    server_themes_dir.mkdir(parents=True, exist_ok=True)
    for xml_file in THEMES_DIR.glob("*.xml"):
        shutil.copy2(xml_file, server_themes_dir / xml_file.name)

    test_cache_dir = OUT_REPORT_DIR / "tile_cache"
    if test_cache_dir.exists():
        shutil.rmtree(test_cache_dir)

    cp = f"{SERVER_DIR / 'MapsforgeTileServer.jar'};{SERVER_DIR / 'lib' / '*'}"
    cmd = [
        JAVA_EXE,
        "-Djava.awt.headless=true",
        "-Xmx1024m",
        "-cp", cp,
        "org.mapsforge.map.layer.renderer.MapsforgeTileServer",
        "--port", str(PORT),
        "--cache-dir", str(test_cache_dir),
        "--themes-dir", str(server_themes_dir),
    ]
    print(f"[Stage-0] Starting MapsforgeTileServer: {' '.join(cmd)}")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    report = {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S+08:00"), "gates": {}}
    try:
        # Wait for /health
        ready = False
        for _ in range(25):
            try:
                st, _, hjson = http_get_json("/health")
                if st == 200 and hjson.get("status") == "ok":
                    ready = True
                    break
            except Exception:
                time.sleep(0.3)
        assert ready, "MapsforgeTileServer failed to start within timeout"

        # =====================================================================
        # Gate G1: .map Auto-Probe (BASEMAP_NO_CONTOUR / BASEMAP_WITH_CONTOUR / CONTOUR_ONLY)
        # =====================================================================
        print("[Stage-0] Running Gate G1 (.map Header & Tag Probe)...")
        _, _, p_official = http_get_json("/api/probe?map=" + urllib.parse.quote(str(MAP_YUNNAN_OFFICIAL)))
        _, _, p_oam = http_get_json("/api/probe?map=" + urllib.parse.quote(str(MAP_YUNNAN_OAM)))
        _, _, p_n27 = http_get_json("/api/probe?map=" + urllib.parse.quote(str(MAP_N27E100)))

        assert p_official["classification"] == "BASEMAP_NO_CONTOUR", f"Unexpected: {p_official}"
        assert p_oam["classification"] == "BASEMAP_WITH_CONTOUR", f"Unexpected: {p_oam}"
        assert p_n27["classification"] == "CONTOUR_ONLY", f"Unexpected: {p_n27}"

        report["gates"]["G1_map_probe"] = {
            "passed": True,
            "yunnan_official": p_official["classification"],
            "ch_yunnan_oam": p_oam["classification"],
            "n27e100_locus": p_n27["classification"],
            "details": {"yunnan.map": p_official["sampleCounts"], "Ch-Yunnan_oam": p_oam["sampleCounts"], "N27E100.map": p_n27["sampleCounts"]},
        }
        print("  -> G1 PASSED:", report["gates"]["G1_map_probe"])

        # =====================================================================
        # Gate G2 & G3: MultiMapDataStore Seamless Stitching (N24E102 + N25E102 across 25.0°N)
        #    & PNG32 Alpha Transparency + WMTS / MapServer Endpoint Verification
        # =====================================================================
        print("[Stage-0] Running Gate G2 & G3 (Multi-Map Stitching & PNG32 Transparency)...")
        # Exact tile at z=13 straddling 25.0°N, 102.65°E (Kunming / Dianchi)
        z_test = 13
        tx_25n, ty_25n = latlon_to_xyz(25.0, 102.65, z_test)
        print(f"  -> Boundary tile at (25.0°N, 102.65°E) z={z_test}: x={tx_25n}, y={ty_25n}")

        # 1) Profile with ONLY N24E102 (South of 25°N)
        http_post_form("/api/profiles", {
            "profileId": "south_only",
            "title": "N24E102 South Only",
            "mapFiles": str(MAP_N24E102),
            "themePath": "ContourSparse.xml",
            "transparent": "true",
            "renderLabels": "true",
        })
        # 2) Profile with ONLY N25E102 (North of 25°N)
        http_post_form("/api/profiles", {
            "profileId": "north_only",
            "title": "N25E102 North Only",
            "mapFiles": str(MAP_N25E102),
            "themePath": "ContourSparse.xml",
            "transparent": "true",
            "renderLabels": "true",
        })
        # 3) Stitched Profile (N24E102 + N25E102)
        _, _, stitched_prof = http_post_form("/api/profiles", {
            "profileId": "dianchi_contour_stitched",
            "title": "滇池 50m 稀疏等高线透明层 (N24E102+N25E102)",
            "mapFiles": f"{MAP_N24E102};{MAP_N25E102}",
            "themePath": "ContourSparse.xml",
            "transparent": "true",
            "renderLabels": "true",
        })

        _, _, b_south = http_get_bytes(f"/tiles/south_only/{z_test}/{tx_25n}/{ty_25n}.png")
        _, _, b_north = http_get_bytes(f"/tiles/north_only/{z_test}/{tx_25n}/{ty_25n}.png")
        _, hdr_stitched, b_stitched = http_get_bytes(f"/tiles/dianchi_contour_stitched/{z_test}/{tx_25n}/{ty_25n}.png")

        stat_south = analyze_png(b_south)
        stat_north = analyze_png(b_north)
        stat_stitched = analyze_png(b_stitched)

        stat_south["image"].save(OUT_REPORT_DIR / "g3_south_only_N24E102.png")
        stat_north["image"].save(OUT_REPORT_DIR / "g3_north_only_N25E102.png")
        stat_stitched["image"].save(OUT_REPORT_DIR / "g3_stitched_N24_N25.png")

        # Verify stitching: stitched visible pixels must be greater than either single map alone,
        # and both top_half (North >= 25°N) and bottom_half (South <= 25°N) must have visible contours!
        assert stat_stitched["top_half_visible"] > 0 and stat_stitched["bottom_half_visible"] > 0
        assert stat_stitched["visible_pixels"] > stat_south["visible_pixels"]
        assert stat_stitched["visible_pixels"] > stat_north["visible_pixels"]
        assert 0.05 < stat_stitched["transparent_ratio"] < 0.99

        # Also verify WMTS and ArcGIS MapServer endpoints on the stitched profile
        wmts_status, _, wmts_bytes = http_get_bytes("/wmts/dianchi_contour_stitched/1.0.0/WMTSCapabilities.xml")
        assert wmts_status == 200 and b"GoogleMapsCompatible" in wmts_bytes
        ms_status, _, ms_json = http_get_json("/arcgis/rest/services/dianchi_contour_stitched/MapServer?f=json")
        assert ms_status == 200 and ms_json.get("singleFusedMapCache") is True
        # Note Esri MapServer order: /tile/{z}/{y}/{x}
        ms_tile_status, ms_tile_hdr, ms_tile_bytes = http_get_bytes(
            f"/arcgis/rest/services/dianchi_contour_stitched/MapServer/tile/{z_test}/{ty_25n}/{tx_25n}")
        assert ms_tile_status == 200 and ms_tile_hdr.get("x-tile-cache") == "HIT", f"Got headers: {ms_tile_hdr}"

        report["gates"]["G2_png32_and_protocols"] = {
            "passed": True,
            "transparent_ratio": stat_stitched["transparent_ratio"],
            "visible_ratio": stat_stitched["visible_ratio"],
            "wmts_capabilities_bytes": len(wmts_bytes),
            "mapserver_tile_cache_hit": ms_tile_hdr.get("x-tile-cache"),
        }
        report["gates"]["G3_multimap_stitching"] = {
            "passed": True,
            "tile": f"{z_test}/{tx_25n}/{ty_25n}",
            "south_only_visible_px": stat_south["visible_pixels"],
            "north_only_visible_px": stat_north["visible_pixels"],
            "stitched_visible_px": stat_stitched["visible_pixels"],
            "stitched_top_half_px": stat_stitched["top_half_visible"],
            "stitched_bottom_half_px": stat_stitched["bottom_half_visible"],
        }
        print("  -> G2 & G3 PASSED:", report["gates"]["G3_multimap_stitching"])

        # =====================================================================
        # Gate G4: Theme Hot-Switch, CacheKey Isolation & dp-Unit Stripper
        # =====================================================================
        print("[Stage-0] Running Gate G4 (Theme Hot-Switch, CacheKey & dp-Unit Stripper)...")
        # Register road+label overlay profile on Ch-Yunnan_oam.osm.map excluding contour & hatch
        _, _, road_prof = http_post_form("/api/profiles", {
            "profileId": "yunnan_roads_overlay",
            "title": "云南户外路网与注记透明层 (LocusSat, 剔除等高线)",
            "mapFiles": str(MAP_YUNNAN_OAM),
            "themePath": "LocusSat.xml",
            "transparent": "true",
            "renderLabels": "true",
            "excludeCats": "contour,hatch",
        })
        _, hdr_road1, b_road = http_get_bytes(f"/tiles/yunnan_roads_overlay/{z_test}/{tx_25n}/{ty_25n}.png")
        stat_road = analyze_png(b_road)
        stat_road["image"].save(OUT_REPORT_DIR / "g4_locussat_roads_overlay.png")

        # Register full outdoor profile using OutdoorFull.xml (which has 'dp' units!)
        _, _, full_prof = http_post_form("/api/profiles", {
            "profileId": "yunnan_outdoor_full",
            "title": "云南全要素户外地形底图 (OutdoorFull, 含dp单位自动剥离)",
            "mapFiles": str(MAP_YUNNAN_OAM),
            "themePath": "OutdoorFull.xml",
            "transparent": "false",
            "renderLabels": "true",
            "excludeCats": "",
        })
        _, hdr_full, b_full = http_get_bytes(f"/tiles/yunnan_outdoor_full/{z_test}/{tx_25n}/{ty_25n}.png")
        stat_full = analyze_png(b_full)
        stat_full["image"].save(OUT_REPORT_DIR / "g4_outdoor_full_basemap.png")

        assert road_prof["cacheKey"] != full_prof["cacheKey"]
        assert road_prof["cacheKey"] != stitched_prof["cacheKey"]
        assert stat_road["visible_pixels"] > 500
        assert stat_full["visible_pixels"] == 256 * 256  # Opaque background

        report["gates"]["G4_theme_switch_and_dp_strip"] = {
            "passed": True,
            "cacheKey_contour": stitched_prof["cacheKey"],
            "cacheKey_roads_overlay": road_prof["cacheKey"],
            "cacheKey_outdoor_full": full_prof["cacheKey"],
            "roads_overlay_visible_px": stat_road["visible_pixels"],
            "outdoor_full_opaque_px": stat_full["visible_pixels"],
        }
        print("  -> G4 PASSED:", report["gates"]["G4_theme_switch_and_dp_strip"])

        # =====================================================================
        # Gate G5: GCJ-02 -> WGS-84 Real-Time Rectification & Compliance Guard
        # =====================================================================
        print("[Stage-0] Running Gate G5 (GCJ-02 Rectification & Border-Trigger Compliance Guard)...")
        _, hdr_raw, b_amap_raw = http_get_bytes(f"/proxy/amap_sat/{z_test}/{tx_25n}/{ty_25n}.png?raw=true")
        _, hdr_corr, b_amap_corr = http_get_bytes(f"/proxy/amap_sat/{z_test}/{tx_25n}/{ty_25n}.png")
        img_raw = Image.open(io.BytesIO(b_amap_raw)).convert("RGBA")
        img_corr = Image.open(io.BytesIO(b_amap_corr)).convert("RGBA")
        img_raw.save(OUT_REPORT_DIR / "g5_amap_sat_raw_gcj02.png")
        img_corr.save(OUT_REPORT_DIR / "g5_amap_sat_rectified_wgs84.png")

        # Compute mean absolute pixel difference to prove geometric shift was applied
        raw_px = list(img_raw.getdata())
        corr_px = list(img_corr.getdata())
        diff_pixels = sum(1 for p1, p2 in zip(raw_px, corr_px) if abs(p1[0] - p2[0]) + abs(p1[1] - p2[1]) + abs(p1[2] - p2[2]) > 8)
        assert hdr_corr.get("x-gcj02-corrected") == "true"
        assert diff_pixels > 5000, f"Expected significant pixel shift after GCJ02->WGS84 rectification, got {diff_pixels}"

        # Compliance guard: test border trigger at macro zoom (z=5) or hasBorder=true on non-whitelist foreign political source
        blocked_code = None
        try:
            http_get_bytes("/proxy/opentopomap/5/25/13.png?hasBorder=true")
        except urllib.error.HTTPError as he:
            blocked_code = he.code
        assert blocked_code == 451, f"Expected HTTP 451 compliance block, got {blocked_code}"
        # Reset hasNationalBorderInView=false
        http_post_form("/api/mode", {"hasNationalBorderInView": "false"})

        report["gates"]["G5_gcj02_and_compliance"] = {
            "passed": True,
            "gcj02_corrected_header": hdr_corr.get("x-gcj02-corrected"),
            "shifted_pixels_out_of_65536": diff_pixels,
            "foreign_border_basemap_blocked_http_code": blocked_code,
        }
        print("  -> G5 PASSED:", report["gates"]["G5_gcj02_and_compliance"])

        # =====================================================================
        # Gate G6: Offline Mode Zero-Leakage & 3-Layer Composite Visual Synthesis
        # =====================================================================
        print("[Stage-0] Running Gate G6 (Offline Mode & 3-Layer Golden Composite Stack)...")
        http_post_form("/api/mode", {"offlineMode": "true"})
        offline_blocked_code = None
        try:
            http_get_bytes(f"/proxy/amap_sat/{z_test}/{tx_25n + 1}/{ty_25n}.png")
        except urllib.error.HTTPError as he:
            offline_blocked_code = he.code
        assert offline_blocked_code == 503, f"Expected HTTP 503 in offline mode, got {offline_blocked_code}"

        # Offline tile rendering must still succeed 100% in offline mode
        st_off, _, _ = http_get_bytes(f"/tiles/dianchi_contour_stitched/{z_test}/{tx_25n}/{ty_25n}.png")
        assert st_off == 200
        http_post_form("/api/mode", {"offlineMode": "false"})

        # Build 4-panel visual comparison sheet:
        # Panel 1: Rectified Satellite Base (amap_sat WGS-84)
        # Panel 2: Stitched 50m Contour Sparse Layer (N24E102 + N25E102)
        # Panel 3: LocusSat Road + Label Overlay (Ch-Yunnan_oam)
        # Panel 4: Golden 3-Layer Composite (Sat + Contour 85% + Roads/Labels 100%)
        comp = img_corr.copy()
        comp = Image.alpha_composite(comp, stat_stitched["image"])
        comp = Image.alpha_composite(comp, stat_road["image"])
        comp.save(OUT_REPORT_DIR / "g6_golden_3layer_composite.png")

        sheet = Image.new("RGBA", (256 * 4 + 50, 310), (24, 28, 36, 255))
        draw = ImageDraw.Draw(sheet)
        panels = [
            (img_corr, "1. Sat Base (GCJ02->WGS84)"),
            (stat_stitched["image"], "2. Stitched Contour (N24+N25)"),
            (stat_road["image"], "3. LocusSat Roads/Labels"),
            (comp, "4. 3-Layer Golden Composite"),
        ]
        for idx, (pimg, label) in enumerate(panels):
            x_off = 10 + idx * 266
            # Checkerboard for transparent layers
            bg = Image.new("RGBA", (256, 256), (245, 242, 235, 255))
            if idx in (1, 2):
                cb_draw = ImageDraw.Draw(bg)
                for cy in range(0, 256, 16):
                    for cx in range(0, 256, 16):
                        if ((cx // 16) + (cy // 16)) % 2 == 1:
                            cb_draw.rectangle([cx, cy, cx + 15, cy + 15], fill=(220, 218, 210, 255))
            merged = Image.alpha_composite(bg, pimg)
            sheet.paste(merged, (x_off, 40))
            draw.text((x_off + 6, 12), label, fill=(240, 245, 255, 255))

        sheet_path = OUT_REPORT_DIR / "stage0_4panel_visual_verification.png"
        sheet.save(sheet_path)

        report["gates"]["G6_offline_and_composite"] = {
            "passed": True,
            "offline_proxy_blocked_http_code": offline_blocked_code,
            "offline_local_tile_http_code": st_off,
            "composite_sheet": str(sheet_path),
        }
        print("  -> G6 PASSED:", report["gates"]["G6_offline_and_composite"])

        report["overall_status"] = "ALL_6_GATES_PASSED"
        report_file = OUT_REPORT_DIR / "stage0_verification_report.json"
        report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[Stage-0] SUCCESS! Report saved to {report_file}")

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    main()
