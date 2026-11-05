# Quickstart: Mod Authoring CLI

Create a module and validate it from the project root:

```powershell
openpower mod create weather_pack
openpower mod validate weather_pack
```

Create a module with a display name and explicit dependencies:

```powershell
openpower mod create weather_pack --name "Weather Pack" --depends base energy_crisis
openpower mod validate weather_pack
```

Use `--project-root` when operating on another checkout:

```powershell
openpower mod create weather_pack --project-root C:/work/OpenPower
openpower mod validate weather_pack --project-root C:/work/OpenPower
```

Successful validation reports the module load order, system count, schema count, state
tables, and handled action count. This guide records the current workflow; commands were
not executed during the documentation-only specification update.
