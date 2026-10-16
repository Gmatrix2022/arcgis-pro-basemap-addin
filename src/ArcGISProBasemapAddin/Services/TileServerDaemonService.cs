using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Net.Http;
using System.Reflection;
using System.Text.Json;
using System.Threading.Tasks;

namespace ArcGISProBasemapAddin.Services
{
    public sealed class MapProbeResult
    {
        public string File { get; set; } = "";
        public long FileSize { get; set; }
        public string Classification { get; set; } = "UNKNOWN";
        public int Highways { get; set; }
        public int Contours { get; set; }
        public int Water { get; set; }
        public int Pois { get; set; }
        public double MinLat { get; set; }
        public double MinLon { get; set; }
        public double MaxLat { get; set; }
        public double MaxLon { get; set; }
    }

    /// <summary>
    /// 本地 MapsforgeTileServer 守护进程生命周期与 HTTP 控制客户端
    /// 支持端口自愈 (18765..18775)、工程打开自启动、默认云南/滇池离线图层注册与模式同步。
    /// </summary>
    public sealed class TileServerDaemonService
    {
        public static TileServerDaemonService Instance { get; } = new TileServerDaemonService();

        private readonly HttpClient _http = new() { Timeout = TimeSpan.FromSeconds(12) };
        private Process? _daemonProcess;

        public int ActivePort { get; private set; } = 18765;
        public string BaseUrl => $"http://127.0.0.1:{ActivePort}";
        public bool IsRunning { get; private set; }
        public bool OfflineMode { get; private set; }
        public bool HasNationalBorderInView { get; private set; }

        // 默认本机离线数据路径（只读引用，绝不写入）
        public const string DefaultWorkspaceInbox = @"D:\AIAssistant\GeoAI地理空间地图创作智能体\data\_inbox";
        public const string DefaultProjectRoot = @"D:\AIAssistant\GeoAI地理空间地图创作智能体\projects\arcgis-pro-basemap-addin";

        public async Task<bool> EnsureRunningAsync()
        {
            // 1. 先检查默认端口或当前端口是否已有健康实例
            if (await CheckHealthAsync(ActivePort))
            {
                IsRunning = true;
                await RegisterDefaultProfilesIfAvailableAsync();
                return true;
            }

            // 2. 查找 Java 与 Server Jar 路径
            string javaExe = FindJavaExecutable();
            string serverDir = FindServerDirectory();
            if (string.IsNullOrEmpty(javaExe) || string.IsNullOrEmpty(serverDir))
            {
                IsRunning = false;
                return false;
            }

            // 3. 端口探测与守护进程拉起
            for (int candidatePort = 18765; candidatePort <= 18775; candidatePort++)
            {
                if (await CheckHealthAsync(candidatePort))
                {
                    ActivePort = candidatePort;
                    IsRunning = true;
                    await RegisterDefaultProfilesIfAvailableAsync();
                    return true;
                }

                if (TryStartDaemonProcess(javaExe, serverDir, candidatePort))
                {
                    for (int attempt = 0; attempt < 15; attempt++)
                    {
                        await Task.Delay(300);
                        if (await CheckHealthAsync(candidatePort))
                        {
                            ActivePort = candidatePort;
                            IsRunning = true;
                            await RegisterDefaultProfilesIfAvailableAsync();
                            return true;
                        }
                    }
                }
            }

            IsRunning = false;
            return false;
        }

        public async Task<bool> CheckHealthAsync(int? portOverride = null)
        {
            int p = portOverride ?? ActivePort;
            try
            {
                using var resp = await _http.GetAsync($"http://127.0.0.1:{p}/health");
                if (!resp.IsSuccessStatusCode) return false;
                string body = await resp.Content.ReadAsStringAsync();
                return body.Contains("\"status\":\"ok\"", StringComparison.OrdinalIgnoreCase);
            }
            catch
            {
                return false;
            }
        }

        private bool TryStartDaemonProcess(string javaExe, string serverDir, int port)
        {
            try
            {
                string jarPath = Path.Combine(serverDir, "MapsforgeTileServer.jar");
                string libWildcard = Path.Combine(serverDir, "lib", "*");
                string themesDir = Path.Combine(serverDir, "themes");
                if (!Directory.Exists(themesDir))
                {
                    themesDir = Path.Combine(DefaultProjectRoot, "themes");
                }

                string localAppData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
                string cacheDir = Path.Combine(localAppData, "GeoAI", "ArcGISProBasemapAddin", "TileCache");
                Directory.CreateDirectory(cacheDir);

                var psi = new ProcessStartInfo
                {
                    FileName = javaExe,
                    Arguments = $"-Djava.awt.headless=true -Xmx1024m -cp \"{jarPath};{libWildcard}\" org.mapsforge.map.layer.renderer.MapsforgeTileServer --port {port} --cache-dir \"{cacheDir}\" --themes-dir \"{themesDir}\"",
                    WorkingDirectory = serverDir,
                    CreateNoWindow = true,
                    UseShellExecute = false,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true
                };
                _daemonProcess = Process.Start(psi);
                return _daemonProcess != null && !_daemonProcess.HasExited;
            }
            catch
            {
                return false;
            }
        }

        public async Task RegisterDefaultProfilesIfAvailableAsync()
        {
            string n24 = Path.Combine(DefaultWorkspaceInbox, @"locus\mapsVector\N24E102.map");
            string n25 = Path.Combine(DefaultWorkspaceInbox, @"locus\mapsVector\N25E102.map");
            string oamYunnan = Path.Combine(DefaultWorkspaceInbox, "Ch-Yunnan_oam.osm.map");

            if (File.Exists(n24) && File.Exists(n25))
            {
                await RegisterProfileAsync(
                    "dianchi_contour_sparse",
                    "滇池 50m 稀疏等高线透明层 (N24E102+N25E102)",
                    $"{n24};{n25}",
                    "ContourSparse.xml",
                    transparent: true,
                    renderLabels: true,
                    excludeCats: "");
            }

            if (File.Exists(oamYunnan))
            {
                await RegisterProfileAsync(
                    "yunnan_roads_overlay",
                    "云南户外路网与注记透明层 (LocusSat)",
                    oamYunnan,
                    "LocusSat.xml",
                    transparent: true,
                    renderLabels: true,
                    excludeCats: "contour,hatch");

                await RegisterProfileAsync(
                    "yunnan_outdoor_full",
                    "云南全要素离线户外地形底图 (OutdoorFull)",
                    oamYunnan,
                    "OutdoorFull.xml",
                    transparent: false,
                    renderLabels: true,
                    excludeCats: "");
            }
        }

        public async Task<bool> RegisterProfileAsync(
            string profileId,
            string title,
            string mapFilesJoined,
            string themePath,
            bool transparent,
            bool renderLabels,
            string excludeCats)
        {
            try
            {
                var form = new FormUrlEncodedContent(new Dictionary<string, string>
                {
                    ["profileId"] = profileId,
                    ["title"] = title,
                    ["mapFiles"] = mapFilesJoined,
                    ["themePath"] = themePath,
                    ["transparent"] = transparent ? "true" : "false",
                    ["renderLabels"] = renderLabels ? "true" : "false",
                    ["excludeCats"] = excludeCats ?? ""
                });
                using var resp = await _http.PostAsync($"{BaseUrl}/api/profiles", form);
                return resp.IsSuccessStatusCode;
            }
            catch
            {
                return false;
            }
        }

        public async Task<MapProbeResult?> ProbeMapFileAsync(string mapFilePath)
        {
            if (!await EnsureRunningAsync()) return null;
            try
            {
                string encoded = Uri.EscapeDataString(mapFilePath);
                using var resp = await _http.GetAsync($"{BaseUrl}/api/probe?map={encoded}");
                if (!resp.IsSuccessStatusCode) return null;
                using var doc = await JsonDocument.ParseAsync(await resp.Content.ReadAsStreamAsync());
                var root = doc.RootElement;
                var counts = root.GetProperty("sampleCounts");
                var bbox = root.GetProperty("bbox");
                return new MapProbeResult
                {
                    File = mapFilePath,
                    FileSize = root.GetProperty("fileSize").GetInt64(),
                    Classification = root.GetProperty("classification").GetString() ?? "UNKNOWN",
                    Highways = counts.GetProperty("highways").GetInt32(),
                    Contours = counts.GetProperty("contours").GetInt32(),
                    Water = counts.GetProperty("water").GetInt32(),
                    Pois = counts.GetProperty("pois").GetInt32(),
                    MinLat = bbox.GetProperty("minLat").GetDouble(),
                    MinLon = bbox.GetProperty("minLon").GetDouble(),
                    MaxLat = bbox.GetProperty("maxLat").GetDouble(),
                    MaxLon = bbox.GetProperty("maxLon").GetDouble()
                };
            }
            catch
            {
                return null;
            }
        }

        public async Task SetModeAsync(bool offlineMode, bool hasNationalBorderInView)
        {
            OfflineMode = offlineMode;
            HasNationalBorderInView = hasNationalBorderInView;
            if (!IsRunning) return;
            try
            {
                var form = new FormUrlEncodedContent(new Dictionary<string, string>
                {
                    ["offlineMode"] = offlineMode ? "true" : "false",
                    ["hasNationalBorderInView"] = hasNationalBorderInView ? "true" : "false"
                });
                await _http.PostAsync($"{BaseUrl}/api/mode", form);
            }
            catch
            {
                // Ignore transient errors
            }
        }

        public void ShutdownIfOwned()
        {
            try
            {
                if (_daemonProcess != null && !_daemonProcess.HasExited)
                {
                    _daemonProcess.Kill(true);
                    _daemonProcess.Dispose();
                    _daemonProcess = null;
                }
            }
            catch
            {
                // Ignore shutdown errors
            }
        }

        private static string FindJavaExecutable()
        {
            string[] candidates =
            {
                @"C:\Program Files\Java\jdk-17\bin\java.exe",
                @"C:\Program Files\Common Files\Oracle\Java\javapath\java.exe",
                @"C:\Program Files\Java\jdk-11.0.17\bin\java.exe"
            };
            foreach (var c in candidates)
            {
                if (File.Exists(c)) return c;
            }
            return "java.exe";
        }

        private static string FindServerDirectory()
        {
            // 1. Check alongside deployed Add-In assembly (Server/ subfolder unpacked by Pro)
            string asmDir = Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location) ?? "";
            string bundledServer = Path.Combine(asmDir, "Server");
            if (File.Exists(Path.Combine(bundledServer, "MapsforgeTileServer.jar")))
            {
                return bundledServer;
            }

            // 2. Fallback to workspace project bin/Server
            string workspaceServer = Path.Combine(DefaultProjectRoot, @"bin\Server");
            if (File.Exists(Path.Combine(workspaceServer, "MapsforgeTileServer.jar")))
            {
                return workspaceServer;
            }
            return "";
        }
    }
}
