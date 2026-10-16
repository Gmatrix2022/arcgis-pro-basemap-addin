using System;
using System.Linq;
using System.Threading.Tasks;
using ArcGIS.Core.Geometry;
using ArcGIS.Desktop.Framework.Threading.Tasks;
using ArcGIS.Desktop.Mapping;

namespace ArcGISProBasemapAddin.Services
{
    /// <summary>
    /// ArcGIS Pro 图层树与黄金三层拆层合成调度服务（严格运行于 MCT QueuedTask.Run 线程）
    /// 图层栈顺序约定（由上至下）：
    /// [0] 户外路网与注记透明层 (LocusSat.xml, 透明度 0%)
    /// [1] 50m 稀疏等高线透明层 (ContourSparse.xml, 透明度 15%)
    /// [2] 卫星底图 / 基础地形底图 (高德实时纠偏卫图 / Esri Imagery, 透明度 0%)
    /// </summary>
    public sealed class ProLayerManagerService
    {
        public static ProLayerManagerService Instance { get; } = new ProLayerManagerService();

        public const string ManagedGroupName = "GeoAI 复合底图与离线矢量栈";

        public async Task<(bool Success, string Message)> AddOrUpdateServiceLayerAsync(
            string serviceId,
            string displayName,
            double transparencyPercent = 0.0,
            bool placeAtTop = true,
            double? zoomMinLon = null,
            double? zoomMinLat = null,
            double? zoomMaxLon = null,
            double? zoomMaxLat = null)
        {
            if (!await TileServerDaemonService.Instance.EnsureRunningAsync())
            {
                return (false, "本地 MapsforgeTileServer 瓦片服务未就绪（请检查 JDK 17 与 18765 端口）。");
            }

            string baseUrl = TileServerDaemonService.Instance.BaseUrl;
            // 优先使用伪装的 ArcGIS REST MapServer 端点，Pro 3.7 原生毫秒级识别瓦片矩阵与 LODs
            string mapServerUrl = $"{baseUrl}/arcgis/rest/services/{serviceId}/MapServer";
            string wmtsFallbackUrl = $"{baseUrl}/wmts/{serviceId}/1.0.0/WMTSCapabilities.xml";

            return await QueuedTask.Run(() =>
            {
                var mapView = MapView.Active;
                var map = mapView?.Map;
                if (map == null)
                {
                    return (false, "当前没有活动的地图视图 (MapView.Active 为空)，请先打开一个地图。");
                }

                // 查找或创建受管图层组
                var groupLayer = map.Layers.OfType<GroupLayer>()
                    .FirstOrDefault(g => string.Equals(g.Name, ManagedGroupName, StringComparison.OrdinalIgnoreCase));
                if (groupLayer == null)
                {
                    groupLayer = LayerFactory.Instance.CreateGroupLayer(map, 0, ManagedGroupName);
                }

                // 若同名图层已存在则先移除，确保新主题/CacheKey 立即生效
                var existing = groupLayer.Layers.FirstOrDefault(l => string.Equals(l.Name, displayName, StringComparison.OrdinalIgnoreCase));
                if (existing != null)
                {
                    map.RemoveLayer(existing);
                }

                int insertIndex = placeAtTop ? 0 : groupLayer.Layers.Count;
                Layer? createdLayer = null;
                try
                {
                    createdLayer = LayerFactory.Instance.CreateLayer(new Uri(mapServerUrl), groupLayer, insertIndex, displayName);
                }
                catch
                {
                    try
                    {
                        createdLayer = LayerFactory.Instance.CreateLayer(new Uri(wmtsFallbackUrl), groupLayer, insertIndex, displayName);
                    }
                    catch (Exception ex2)
                    {
                        return (false, $"创建图层失败：{ex2.Message}");
                    }
                }

                if (createdLayer == null)
                {
                    return (false, $"LayerFactory 未能从 {mapServerUrl} 创建图层。");
                }

                createdLayer.SetVisibility(true);
                if (transparencyPercent > 0.1)
                {
                    createdLayer.SetTransparency(Math.Clamp(transparencyPercent, 0.0, 95.0));
                }

                if (zoomMinLon.HasValue && zoomMinLat.HasValue && zoomMaxLon.HasValue && zoomMaxLat.HasValue && mapView != null)
                {
                    var env = EnvelopeBuilderEx.CreateEnvelope(
                        zoomMinLon.Value, zoomMinLat.Value, zoomMaxLon.Value, zoomMaxLat.Value, SpatialReferences.WGS84);
                    mapView.ZoomTo(env, TimeSpan.FromMilliseconds(600));
                }

                return (true, $"已挂载图层：【{displayName}】（端口 {TileServerDaemonService.Instance.ActivePort}）");
            });
        }

        /// <summary>
        /// 一键装配「滇池/云南黄金三层复合底图栈」：
        /// 底层：高德卫星实时纠偏 (WGS-84)
        /// 中层：N24E102 + N25E102 跨纬线无缝拼接 50m 稀疏等高线透明层 (ContourSparse.xml)
        /// 顶层：Ch-Yunnan_oam 户外路网与注记透明层 (LocusSat.xml, 剔除等高线与保护区绿斜纹)
        /// </summary>
        public async Task<(bool Success, string Message)> LoadGoldenThreeLayerStackAsync()
        {
            if (!await TileServerDaemonService.Instance.EnsureRunningAsync())
            {
                return (false, "MapsforgeTileServer 启动失败。");
            }

            await TileServerDaemonService.Instance.RegisterDefaultProfilesIfAvailableAsync();

            // 1. 底层：高德实时纠偏卫星底图 (WGS-84)
            if (!TileServerDaemonService.Instance.OfflineMode)
            {
                await AddOrUpdateServiceLayerAsync(
                    "proxy_amap_sat",
                    "1. [底图] 高德卫星影像 (GCJ-02→WGS-84 实时纠偏)",
                    transparencyPercent: 0.0,
                    placeAtTop: false);
            }

            // 2. 中层：滇池 50m 稀疏等高线透明层 (N24E102 + N25E102)
            await AddOrUpdateServiceLayerAsync(
                "dianchi_contour_sparse",
                "2. [等高线] 滇池 50m 稀疏等高线透明层 (N24+N25 无缝拼接)",
                transparencyPercent: 12.0,
                placeAtTop: true);

            // 3. 顶层：云南户外路网与注记透明层 (LocusSat, 剔除 contour,hatch) + 缩放至昆明滇池/西山视野
            var res = await AddOrUpdateServiceLayerAsync(
                "yunnan_roads_overlay",
                "3. [路网注记] 云南户外分级路网与山峰注记 (LocusSat)",
                transparencyPercent: 0.0,
                placeAtTop: true,
                zoomMinLon: 102.58,
                zoomMinLat: 24.92,
                zoomMaxLon: 102.75,
                zoomMaxLat: 25.06);

            return res.Success
                ? (true, "已成功构建【黄金三层复合底图栈】：1.纠偏卫图 → 2.50m稀疏等高线 → 3.LocusSat户外路网注记，并已定位至昆明滇池-西山区域。")
                : res;
        }
    }
}
