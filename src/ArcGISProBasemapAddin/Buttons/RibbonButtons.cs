using System;
using ArcGIS.Desktop.Framework;
using ArcGIS.Desktop.Framework.Contracts;
using ArcGIS.Desktop.Framework.Dialogs;
using ArcGISProBasemapAddin.Services;
using ArcGISProBasemapAddin.ViewModels;

namespace ArcGISProBasemapAddin.Buttons
{
    internal class ShowBasemapDockPaneButton : Button
    {
        protected override void OnClick()
        {
            BasemapDockPaneViewModel.Show();
        }
    }

    internal class CheckDaemonStatusButton : Button
    {
        protected override async void OnClick()
        {
            try
            {
                bool ok = await TileServerDaemonService.Instance.EnsureRunningAsync();
                if (ok)
                {
                    MessageBox.Show(
                        $"本地 MapsforgeTileServer (0.25.0) 瓦片引擎运行正常！\n\n" +
                        $"监听地址：{TileServerDaemonService.Instance.BaseUrl}\n" +
                        $"离线断网模式：{(TileServerDaemonService.Instance.OfflineMode ? "开启" : "关闭")}\n" +
                        $"已自动注册：滇池 50m 等高线拼接包 (N24+N25)、云南户外路网叠加层 (LocusSat)、云南全要素地形图 (OutdoorFull)。",
                        "GeoAI 瓦片引擎自检通过");
                }
                else
                {
                    MessageBox.Show(
                        "未能拉起本地 MapsforgeTileServer 瓦片服务，请检查 JDK 17 与 Server/MapsforgeTileServer.jar 是否完整。",
                        "GeoAI 瓦片引擎告警");
                }
            }
            catch (Exception ex)
            {
                MessageBox.Show($"自检异常：{ex.Message}", "GeoAI 瓦片引擎错误");
            }
        }
    }

    internal class LoadGoldenStackPresetButton : Button
    {
        protected override async void OnClick()
        {
            try
            {
                var (ok, msg) = await ProLayerManagerService.Instance.LoadGoldenThreeLayerStackAsync();
                if (!ok)
                {
                    MessageBox.Show(msg, "GeoAI 黄金三层栈提示");
                }
            }
            catch (Exception ex)
            {
                MessageBox.Show($"加载黄金三层栈异常：{ex.Message}", "GeoAI 错误");
            }
        }
    }

    internal class LoadOutdoorFullPresetButton : Button
    {
        protected override async void OnClick()
        {
            try
            {
                await TileServerDaemonService.Instance.EnsureRunningAsync();
                var (ok, msg) = await ProLayerManagerService.Instance.AddOrUpdateServiceLayerAsync(
                    "yunnan_outdoor_full",
                    "[离线底图] 云南全要素户外地形图 (OutdoorFull)",
                    transparencyPercent: 0.0,
                    placeAtTop: false,
                    zoomMinLon: 102.58,
                    zoomMinLat: 24.92,
                    zoomMaxLon: 102.75,
                    zoomMaxLat: 25.06);
                if (!ok)
                {
                    MessageBox.Show(msg, "GeoAI 离线地形图提示");
                }
            }
            catch (Exception ex)
            {
                MessageBox.Show($"加载全要素地形图异常：{ex.Message}", "GeoAI 错误");
            }
        }
    }

    internal class LoadAmapSatPresetButton : Button
    {
        protected override async void OnClick()
        {
            try
            {
                var (allowed, reason) = ComplianceGuardService.Instance.ValidateOnlineSource(
                    "amap_sat",
                    "https://webst01.is.autonavi.com",
                    TileServerDaemonService.Instance.HasNationalBorderInView,
                    TileServerDaemonService.Instance.OfflineMode);
                if (!allowed)
                {
                    MessageBox.Show(reason, "GeoAI 合规与离线守卫拦截");
                    return;
                }

                var (ok, msg) = await ProLayerManagerService.Instance.AddOrUpdateServiceLayerAsync(
                    "proxy_amap_sat",
                    "[合规底图] 高德卫星影像 (GCJ-02→WGS-84 实时纠偏)",
                    transparencyPercent: 0.0,
                    placeAtTop: false,
                    zoomMinLon: 102.58,
                    zoomMinLat: 24.92,
                    zoomMaxLon: 102.75,
                    zoomMaxLat: 25.06);
                if (!ok)
                {
                    MessageBox.Show(msg, "GeoAI 在线底图提示");
                }
            }
            catch (Exception ex)
            {
                MessageBox.Show($"加载高德纠偏卫图异常：{ex.Message}", "GeoAI 错误");
            }
        }
    }
}
