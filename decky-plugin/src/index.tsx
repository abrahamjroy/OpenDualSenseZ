import {
  definePlugin,
  PanelSection,
  PanelSectionRow,
  ButtonItem,
  Dropdown,
  DropdownItem,
  ToggleField,
  Field,
  ProgressBar,
  ServerAPI,
  staticClasses,
} from "@decky/ui";
import { useState, useEffect, VFC } from "react";
import { FaGamepad, FaBatteryHalf, FaCar, FaLightbulb, FaBolt } from "react-icons/fa";

interface OpenDSZStatus {
  status: string;
  connected: boolean;
  connection_type: string;
  battery: number;
  is_charging: boolean;
  latency_ms: number;
  polling_rate_hz: number;
  active_profile: string;
  effect: string;
  telemetry: {
    forza_active: boolean;
    forza_port: number;
    dsx_active: boolean;
  };
}

const Content: VFC<{ serverApi: ServerAPI }> = ({ serverApi }) => {
  const [status, setStatus] = useState<OpenDSZStatus | null>(null);
  const [profiles, setProfiles] = useState<string[]>([]);
  const [effects, setEffects] = useState<string[]>([]);
  const [selectedProfile, setSelectedProfile] = useState<string>("default");
  const [selectedEffect, setSelectedEffect] = useState<string>("Ferrari F1 Shift Indicator");
  const [telemetryEnabled, setTelemetryEnabled] = useState<boolean>(true);
  const [loading, setLoading] = useState<boolean>(false);

  const fetchState = async () => {
    try {
      const res = await serverApi.callPluginMethod<{}, OpenDSZStatus>("get_status", {});
      if (res.success && res.result) {
        setStatus(res.result);
        setSelectedProfile(res.result.active_profile);
        setSelectedEffect(res.result.effect);
        setTelemetryEnabled(res.result.telemetry?.forza_active ?? true);
      }
    } catch (e) {
      console.error("[OpenDSZ Decky] Error fetching status:", e);
    }
  };

  const fetchOptions = async () => {
    try {
      const profRes = await serverApi.callPluginMethod<{}, { profiles: string[] }>("get_profiles", {});
      if (profRes.success && profRes.result?.profiles) {
        setProfiles(profRes.result.profiles);
      }
      const effRes = await serverApi.callPluginMethod<{}, { effects: string[] }>("get_effects", {});
      if (effRes.success && effRes.result?.effects) {
        setEffects(effRes.result.effects);
      }
    } catch (e) {
      console.error("[OpenDSZ Decky] Error fetching options:", e);
    }
  };

  useEffect(() => {
    fetchState();
    fetchOptions();
    const interval = setInterval(fetchState, 2500);
    return () => clearInterval(interval);
  }, []);

  const handleProfileChange = async (item: DropdownItem) => {
    const name = item.data as string;
    setSelectedProfile(name);
    setLoading(true);
    try {
      await serverApi.callPluginMethod<{ name: string }, any>("set_profile", { name });
      await fetchState();
    } finally {
      setLoading(false);
    }
  };

  const handleEffectChange = async (item: DropdownItem) => {
    const eff = item.data as string;
    setSelectedEffect(eff);
    try {
      await serverApi.callPluginMethod<{ effect: string }, any>("set_effect", { effect: eff });
      await fetchState();
    } catch (e) {
      console.error("[OpenDSZ Decky] Error updating effect:", e);
    }
  };

  const handleTelemetryToggle = async (enabled: boolean) => {
    setTelemetryEnabled(enabled);
    try {
      await serverApi.callPluginMethod<{ enabled: boolean; port: number }, any>("set_telemetry", {
        enabled,
        port: 5300,
      });
      await fetchState();
    } catch (e) {
      console.error("[OpenDSZ Decky] Error toggling telemetry:", e);
    }
  };

  const isConnected = status?.connected ?? false;
  const connDesc = isConnected
    ? `${status?.connection_type} (${status?.polling_rate_hz?.toFixed(0)} Hz)`
    : "Disconnected";

  return (
    <PanelSection title="DualSense Controller Status">
      <PanelSectionRow>
        <Field
          label="Device"
          description={connDesc}
          icon={<FaGamepad style={{ color: isConnected ? "#10b981" : "#ef4444" }} />}
        >
          <span style={{ color: isConnected ? "#10b981" : "#ef4444", fontWeight: "bold" }}>
            {isConnected ? "Connected" : "Not Found"}
          </span>
        </Field>
      </PanelSectionRow>

      {isConnected && (
        <PanelSectionRow>
          <Field
            label="Battery Level"
            description={status?.is_charging ? "Charging via USB" : `${status?.battery}% remaining`}
            icon={status?.is_charging ? <FaBolt style={{ color: "#f59e0b" }} /> : <FaBatteryHalf />}
          >
            <div style={{ width: "80px" }}>
              <ProgressBar nProgress={status?.battery ?? 0} />
            </div>
          </Field>
        </PanelSectionRow>
      )}

      <PanelSection title="Game Profiles">
        <PanelSectionRow>
          <Dropdown
            menuLabel="Select Profile"
            rgOptions={
              profiles.length > 0
                ? profiles.map((p) => ({ label: p, data: p }))
                : [{ label: "Default Profile", data: "default" }]
            }
            selectedOption={selectedProfile}
            onChange={handleProfileChange}
            disabled={loading}
          />
        </PanelSectionRow>
      </PanelSection>

      <PanelSection title="Ferrari F1 & RGB Effects">
        <PanelSectionRow>
          <Dropdown
            menuLabel="Lightbar Animation"
            rgOptions={
              effects.length > 0
                ? effects.map((e) => ({ label: e, data: e }))
                : [
                    { label: "Ferrari F1 Shift Indicator", data: "Ferrari F1 Shift Indicator" },
                    { label: "Super Saiyan (Golden Aura)", data: "Super Saiyan (Golden Aura)" },
                    { label: "Breathing", data: "Breathing" },
                    { label: "Rainbow Cycle", data: "Rainbow Cycle" },
                  ]
            }
            selectedOption={selectedEffect}
            onChange={handleEffectChange}
          />
        </PanelSectionRow>
      </PanelSection>

      <PanelSection title="Sim Telemetry Bridge">
        <PanelSectionRow>
          <ToggleField
            label="Forza / SimHub UDP"
            description="Port 5300 (ABS shudder & RPM rev lights)"
            checked={telemetryEnabled}
            onChange={handleTelemetryToggle}
          />
        </PanelSectionRow>
      </PanelSection>

      <PanelSectionRow>
        <ButtonItem
          layout="below"
          onClick={async () => {
            await serverApi.callPluginMethod("reconnect", {});
            await fetchState();
          }}
        >
          Scan / Reconnect Controller
        </ButtonItem>
      </PanelSectionRow>
    </PanelSection>
  );
};

export default definePlugin((serverApi: ServerAPI) => {
  return {
    title: <div className={staticClasses.Title}>OpenDSZ</div>,
    content: <Content serverApi={serverApi} />,
    icon: <FaGamepad />,
    onDismount() {},
  };
});
