# Studio bowl-drop test

This example ships a portable copy of the [Blender scene](scene.blend) used for the paper's studio intervention. The scene is the locally revised reconstruction of Vilhelm Hammershøi's *Interior with the Artist's Easel*. The copy retains the original geometry, rigid bodies, and packed image, and uses relative resource paths. [Painting source](https://open.smk.dk/en/artwork/image/KMS7444)

Run both commands from the repository root with Blender 4.5 LTS. Each command opens a fresh copy of the scene in memory.

```sh
blender --background --disable-autoexec examples/interventions/studio-bowl/scene.blend \
  --python-exit-code 1 --python examples/interventions/studio-bowl/replay.py -- table
blender --background --disable-autoexec examples/interventions/studio-bowl/scene.blend \
  --python-exit-code 1 --python examples/interventions/studio-bowl/replay.py -- floor
```

Both tests raise the bowl by 0.18 m and release it at frame 1. The floor test also moves the bowl beyond the table edge. The script prints the bowl's lowest point at four frames and checks that it settles within 1 cm of the intended surface by frame 80. The scene file is left intact.
