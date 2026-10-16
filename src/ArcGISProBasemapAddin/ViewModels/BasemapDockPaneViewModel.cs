using System;
using System.Collections.ObjectModel;
using System.IO;
using System.Threading.Tasks;
using System.Windows.Input;
using ArcGIS.Desktop.Framework;
using ArcGIS.Desktop.Framework.Contracts;
using ArcGISProBasemapAddin.Services;
using Microsoft.Win32;

namespace ArcGISProBasemapAddin.ViewModels
{
    public sealed class OnlineSourceOption
    {
        public string Id { get; init; } = "";
        public string Title { get; init; } = "";
        public bool IsDomesticWhitelist { get; init; }
    }

    internal class BasemapDockPaneViewModel : DockPane
    {
        private const string DockPaneId = "ArcGISProBasemapAddin_DockPane";

        public ObservableCollection<OnlineSourceOption> OnlineSources { get; } = new()
        {
            new OnlineSourceOption { Id = "amap_sat", Title = "高德卫星影像 (GCJ-02→WGS-84 实时纠偏)", IsDomesticWhitelist = true },
            new OnlineSourceOption { Id = "amap_road", Title = "高德标准路网 (GCJ-02→WGS-84 实时纠偏)", IsDomesticWhitelist = true },
            new OnlineSourceOption { Id = "amap_label_only", Title = "高德纯路网透明叠置层 (style=8, GCJ-02 纠偏)", IsDomesticWhitelist = true },
            new OnlineSourceOption { Id = "esri_imagery", Title = "Esri World Imagery 全球卫星影像 (纯影像无国界)", IsDomesticWhitelist = true },
            new OnlineSourceOption { Id = "opentopomap", Title = "OpenTopoMap 官方地形图 (仅限局部无国界视野)", IsDomesticWhitelist = false },
            new OnlineSourceOption { Id = "osm_standard", Title = "OpenStreetMap 标准底图 (仅限局部无国界视野)", IsDomesticWhitelist = false }
        };

        public ObservableCollection<string> ThemeOptions { get; } = new()
        {
            "LocusSat.xml",
            "ContourSparse.xml",
            "ContourOnly.xml",
            "OutdoorFull.xml"
        };

        private OnlineSourceOption? _selectedOnlineSource;
        public OnlineSourceOption? SelectedOnlineSource
        {
            get => _selectedOnlineSource;
            set => SetProperty(ref _selectedOnlineSource, value);
        }

        private string _selectedMapFiles = @"D:\AIAssistant\GeoAI地理空间地图创作智能体\data\_inbox\Ch-Yunnan_oam.osm.map";
        public string SelectedMapFiles
        {
            get => _selectedMapFiles;
            set => SetProperty(ref _selectedMapFiles, value);
        }

        private string _selectedTheme = "LocusSat.xml";
        public string SelectedTheme
        {
            get => _selectedTheme;
            set => SetProperty(ref _selectedTheme, value);
        }

        private string _excludeCats = "contour,hatch";
        public string ExcludeCats
        {
            get => _excludeCats;
            set => SetProperty(ref _excludeCats, value);
        }

        private bool _transparentOverlay = true;
        public bool TransparentOverlay
        {
            get => _transparentOverlay;
            set => SetProperty(ref _transparentOverlay, value);
        }

        private double _layerTransparency = 0.0;
        public double LayerTransparency
        {
            get => _layerTransparency;
            set => SetProperty(ref _layerTransparency, value);
        }

        private bool _offlineMode;
        public bool OfflineMode
        {
            get => _offlineMode;
            set
            {
                if (SetProperty(ref _offlineMode, value))
                {
                    _ = TileServerDaemonService.Instance.SetModeAsync(_offlineMode, _hasNationalBorderInView);
                    StatusMessage = _offlineMode ? "已切换至【纯离线断网模式】（外部在线请求已全部阻断）" : "已恢复【在线+离线混合模式】";
                }
            }
        }

        private bool _hasNationalBorderInView;
        public bool HasNationalBorderInView
        {
            get => _hasNationalBorderInView;
            set
            {
                if (SetProperty(ref _hasNationalBorderInView, value))
                {
                    _ = TileServerDaemonService.Instance.SetModeAsync(_offlineMode, _hasNationalBorderInView);
                    StatusMessage = _hasNationalBorderInView
                        ? "【国界触发制已激活】当前视图含国界，已强制锁定境内合规白名单图源"
                        : "【局部无国界模式】当前为局部城市/赛道视野，允许加载常规科研/户外图层";
                }
            }
        }

        private string _probeSummary = "尚未探查（点击【探查 .map 属性】自动识别等高线与路网要素）";
        public string ProbeSummary
        {
            get => _probeSummary;
            set => SetProperty(ref _probeSummary, value);
        }

        private string _statusMessage = "就绪 — 本地 MapsforgeTileServer 监听于 127.0.0.1:18765";
        public string StatusMessage
        {
            get => _statusMessage;
            set => SetProperty(ref _statusMessage, value);
        }

        public ICommand BrowseMapFilesCommand { get; }
        public ICommand ProbeMapCommand { get; }
        public ICommand LoadOnlineBasemapCommand { get; }
        public ICommand LoadCustomMapsforgeLayerCommand { get; }
        public ICommand LoadGoldenThreeLayerCommand { get; }

        protected BasemapDockPaneViewModel()
        {
            _selectedOnlineSource = OnlineSources[0];
            BrowseMapFilesCommand = new RelayCommand(OnBrowseMapFiles);
            ProbeMapCommand = new RelayCommand(async () => await OnProbeMapAsync());
            LoadOnlineBasemapCommand = new RelayCommand(async () => await OnLoadOnlineBasemapAsync());
            LoadCustomMapsforgeLayerCommand = new RelayCommand(async () => await OnLoadCustomMapsforgeLayerAsync());
            LoadGoldenThreeLayerCommand = new RelayCommand(async () => await OnLoadGoldenThreeLayerAsync());
        }

        internal static void Show()
        {
            var pane = FrameworkApplication.DockPaneManager.Find(DockPaneId);
            pane?.Activate();
        }

        private void OnBrowseMapFiles()
        {
            var dlg = new OpenFileDialog
            {
                Title = "选择一个或多个 Mapsforge 离线矢量地图 (.map)",
                Filter = "Mapsforge 矢量地图 (*.map)|*.map|所有文件 (*.*)|*.*",
                Multiselect = true
            };
            if (Directory.Exists(TileServerDaemonService.DefaultWorkspaceInbox))
            {
                dlg.InitialDirectory = TileServerDaemonService.DefaultWorkspaceInbox;
            }
            if (dlg.ShowDialog() == true && dlg.FileNames.Length > 0)
            {
                SelectedMapFiles = string.Join(";", dlg.FileNames);
                _ = OnProbeMapAsync();
            }
        }

        private async Task OnProbeMapAsync()
        {
            string firstFile = SelectedMapFiles.Split(';', StringSplitOptions.RemoveEmptyEntries)[0].Trim();
            if (!File.Exists(firstFile))
            {
                ProbeSummary = $"文件不存在：{firstFile}";
                return;
            }
            StatusMessage = "正在探查 .map 头部与中心瓦片要素...";
            var res = await TileServerDaemonService.Instance.ProbeMapFileAsync(firstFile);
            if (res == null)
            {
                ProbeSummary = "探查失败，请确认本地 MapsforgeTileServer 已启动。";
                return;
            }

            ProbeSummary = $"类型：{res.Classification} | 道路：{res.Highways} | 等高线：{res.Contours} | 水系：{res.Water} | 范围：[{res.MinLat:F2},{res.MinLon:F2}]~[{res.MaxLat:F2},{res.MaxLon:F2}]";
            if (res.Classification == "CONTOUR_ONLY")
            {
                SelectedTheme = "ContourSparse.xml";
                ExcludeCats = "";
                TransparentOverlay = true;
                StatusMessage = "已识别为【纯等高线包】，自动推荐主题 ContourSparse.xml（透明叠加）。";
            }
            else if (res.Classification == "BASEMAP_NO_CONTOUR")
            {
                SelectedTheme = "LocusSat.xml";
                ExcludeCats = "hatch";
                StatusMessage = "已识别为【无等高线路网包】，已自动禁用等高线空白项。";
            }
            else
            {
                StatusMessage = "已识别为【含等高线全要素包 (OpenAndroMaps)】，支持三层拆层渲染。";
            }
        }

        private async Task OnLoadOnlineBasemapAsync()
        {
            if (SelectedOnlineSource == null) return;
            var (allowed, reason) = ComplianceGuardService.Instance.ValidateOnlineSource(
                SelectedOnlineSource.Id,
                SelectedOnlineSource.Id,
                HasNationalBorderInView,
                OfflineMode);
            if (!allowed)
            {
                StatusMessage = reason;
                return;
            }

            StatusMessage = $"正在加载在线图层：{SelectedOnlineSource.Title} ...";
            var (ok, msg) = await ProLayerManagerService.Instance.AddOrUpdateServiceLayerAsync(
                $"proxy_{SelectedOnlineSource.Id}",
                $"[在线底图] {SelectedOnlineSource.Title}",
                transparencyPercent: LayerTransparency,
                placeAtTop: false);
            StatusMessage = msg;
        }

        private async Task OnLoadCustomMapsforgeLayerAsync()
        {
            if (string.IsNullOrWhiteSpace(SelectedMapFiles))
            {
                StatusMessage = "请先选择至少一个 .map 文件。";
                return;
            }
            await TileServerDaemonService.Instance.EnsureRunningAsync();
            string profileId = $"custom_{Math.Abs(HashCode.Combine(SelectedMapFiles, SelectedTheme, ExcludeCats, TransparentOverlay))}";
            string shortName = Path.GetFileNameWithoutExtension(SelectedMapFiles.Split(';')[0]);
            string layerTitle = $"[Mapsforge] {shortName} ({SelectedTheme})";

            bool regOk = await TileServerDaemonService.Instance.RegisterProfileAsync(
                profileId,
                layerTitle,
                SelectedMapFiles,
                SelectedTheme,
                TransparentOverlay,
                renderLabels: true,
                excludeCats: ExcludeCats);
            if (!regOk)
            {
                StatusMessage = "向本地瓦片服务注册渲染配置失败，请检查 .map 与主题路径。";
                return;
            }

            var probe = await TileServerDaemonService.Instance.ProbeMapFileAsync(SelectedMapFiles.Split(';')[0].Trim());
            var (ok, msg) = await ProLayerManagerService.Instance.AddOrUpdateServiceLayerAsync(
                profileId,
                layerTitle,
                transparencyPercent: LayerTransparency,
                placeAtTop: TransparentOverlay,
                zoomMinLon: probe?.MinLon,
                zoomMinLat: probe?.MinLat,
                zoomMaxLon: probe?.MaxLon,
                zoomMaxLat: probe?.MaxLat);
            StatusMessage = msg;
        }

        private async Task OnLoadGoldenThreeLayerAsync()
        {
            StatusMessage = "正在装配【黄金三层复合底图栈】...";
            var (_, msg) = await ProLayerManagerService.Instance.LoadGoldenThreeLayerStackAsync();
            StatusMessage = msg;
        }
    }
}
