src/
└── client/
    ├── controllers/        # Input handling & logic (Camera, Selection)
    │   ├── camera_controller.py
    │   └── viewport_controller.py
    ├── interfaces/         # Protocols
    ├── renderers/          # Visuals (Arcade/OpenGL)
    ├── services/           # External bridges (ImGui, Network)
    ├── tasks/              # Background loading
    ├── ui/                 # UI System
    │   ├── components/     # Reusable widgets (Buttons, Progress Bars)
    │   ├── layouts/        # High-level composition of panels
    │   ├── panels/         # Individual UI windows (Inspector, Lists)
    │   ├── composer.py     # UI Factory
    │   └── theme.py
    ├── utils/              # Client-specific helpers
    │   └── color_generator.py
    └── views/              # Arcade View entry points