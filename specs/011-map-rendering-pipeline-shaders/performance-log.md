# Performance Gate Log

Optimization limit: maximum three measured implementation iterations per algorithm. A baseline measurement does not consume an iteration.

| Algorithm / gate | Baseline | Iteration 1 | Iteration 2 | Iteration 3 | Status |
| --- | --- | --- | --- | --- | --- |
| `RegionMapData.get_region_id`, <0.001 ms/query | Median 0.000515 ms/query; p95 0.000891 ms/query. | — | — | — | PASS; 0/3 optimization iterations. |
| Globe/planar map renderer, 60+ FPS at 4K | Globe median 0.399 ms (2508.8 FPS), p95 2.799 ms; planar median 0.577 ms (1734.3 FPS), p95 0.616 ms. | — | — | — | PASS for renderer-only path; 0/3 optimization iterations. |

## Measurement context

- Platform: Windows 11 Pro; AMD Ryzen 5 2600; NVIDIA GeForce RTX 5060 Ti, driver 591.74; Python 3.14.1; NumPy 2.2.6; OpenCV 4.12.0.
- Region lookup: synthetic 512×256 map, 10,000 warmup lookups followed by 11 samples of 10,000 lookups. Direct call timing; threshold is strictly under 0.001 ms/query.
- GPU rendering: production 16,000×8,000 region and terrain maps, hidden 3,840×2,160 OpenGL viewport, 10 warmup frames and 60 measured frames per projection. `glFinish()` synchronizes each measured frame; renderer call and GPU completion are timed together. Cache writes were redirected/disabled for this probe.
- The GPU result measures the map renderer only; UI composition, units, battle effects, and OS presentation are not included. Full application frame time can therefore be lower.
- Shader compilation and representative pixel checks are separately verified by the optional live OpenGL test; they are not used as frame-rate evidence.

No performance optimization iterations were needed: both measured gates passed on the available machine. If a later target machine misses a gate, record each measured change/result and stop after three iterations before continuing feature work.
