using System;
using ArcGIS.Desktop.Core.Events;
using ArcGIS.Desktop.Framework;
using ArcGIS.Desktop.Framework.Contracts;
using ArcGISProBasemapAddin.Services;

namespace ArcGISProBasemapAddin
{
    /// <summary>
    /// GeoAI 多源合规底图与 Mapsforge 离线矢量地图主模块
    /// 订阅 ProjectOpenedEvent 与 ProjectClosingEvent，实现工程打开时自动拉起/自愈本地 MapsforgeTileServer 守护进程。
    /// </summary>
    internal class BasemapModule : Module
    {
        private static BasemapModule? _this;

        public static BasemapModule Current =>
            _this ??= (BasemapModule)FrameworkApplication.FindModule("ArcGISProBasemapAddin_Module");

        protected override bool Initialize()
        {
            ProjectOpenedEvent.Subscribe(OnProjectOpened);
            ProjectClosingEvent.Subscribe(OnProjectClosing);
            _ = TileServerDaemonService.Instance.EnsureRunningAsync();
            return base.Initialize();
        }

        private async void OnProjectOpened(ProjectEventArgs args)
        {
            try
            {
                await TileServerDaemonService.Instance.EnsureRunningAsync();
            }
            catch
            {
                // Non-blocking background initialization
            }
        }

        private System.Threading.Tasks.Task OnProjectClosing(ProjectClosingEventArgs args)
        {
            return System.Threading.Tasks.Task.CompletedTask;
        }

        protected override void Uninitialize()
        {
            ProjectOpenedEvent.Unsubscribe(OnProjectOpened);
            ProjectClosingEvent.Unsubscribe(OnProjectClosing);
            TileServerDaemonService.Instance.ShutdownIfOwned();
            base.Uninitialize();
        }
    }
}
