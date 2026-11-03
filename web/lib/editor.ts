import type { Ketcher } from "ketcher-core";

/** Ketcher reports parser failures through events and resolves setMolecule anyway. */
export async function setEditorMolecule(
  editor: Pick<Ketcher, "setMolecule" | "eventBus">,
  smiles: string,
): Promise<void> {
  let failed = false;
  const onFailure = () => {
    failed = true;
  };
  editor.eventBus.once("FAILURE", onFailure);
  try {
    await editor.setMolecule(smiles);
    if (failed)
      throw new Error("SMILES 无效，请检查后重新载入；当前画布尚未应用到对话");
  } finally {
    editor.eventBus.removeListener("FAILURE", onFailure);
  }
}
