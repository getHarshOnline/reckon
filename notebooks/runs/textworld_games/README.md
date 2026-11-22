# TextWorld inputs used by notebook 06

These games were generated with TextWorld 1.7.0 using seeds 42–56 for the policy comparisons and 1000–1019 for the paired record-removal experiments, with three rooms, five objects and quest length three. Each case keeps its `.z8` executable, `.json` game metadata and generated Inform 7 `.ni` source. The run's `games.json` identifies the executable and metadata hashes actually used; one case can serve several policy comparisons.

The default grammar-directory field in generated JSON is empty so a machine-local installation path is not embedded. Game logic, names, quests and text remain in the file. TextWorld uses its installed default grammar if regeneration needs it. Custom supplied games are not rewritten by the adapter.

Generate cases through [the notebook adapter](../../_utils/adapters/textworld_adapter.py), which sets the generator seed and retains the resulting files here. These are experiment inputs, not evidence that the scripted controller won the games. Read the recorded outcomes and backend in the corresponding notebook run.

Generated with [Microsoft TextWorld](https://github.com/microsoft/TextWorld); its [MIT licence](LICENSE-TextWorld.txt) is preserved here.
