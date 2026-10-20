// Run in a dedicated ComfyUI browser session via playwright-cli run-code.
async page => {
    await page.waitForFunction(async () => {
        const { app } = await import("/scripts/app.js");
        return app.graph && globalThis.LiteGraph?.registered_node_types?.XavierSaveImage
            && globalThis.LiteGraph?.registered_node_types?.EmptyImage
            && globalThis.LiteGraph?.registered_node_types?.PrimitiveStringMultiline;
    });
    return await page.evaluate(async () => {
        const { app } = await import("/scripts/app.js");
        const assert = (value, message) => { if (!value) throw new Error(message); };
        app.graph.clear();
        const source = LiteGraph.createNode("EmptyImage");
        source.pos = [60, 180];
        app.graph.add(source);
        const set = (node, name, value) => {
            const widget = node.widgets.find(w => w.name === name);
            widget.value = value;
            widget.callback?.(value);
        };
        set(source, "width", 256);
        set(source, "height", 256);
        set(source, "batch_size", 2);
        set(source, "color", 0x4080c0);
        const text = LiteGraph.createNode("PrimitiveStringMultiline");
        text.pos = [60, 420];
        app.graph.add(text);
        set(text, "value", "A café in soft natural light.\nDetailed textures.");
        for (const [index, format] of ["PNG", "JPEG"].entries()) {
            const node = LiteGraph.createNode("XavierSaveImage");
            node.pos = [440 + index * 420, 120];
            node.size[0] = 360;
            app.graph.add(node);
            set(node, "format", format);
            set(node, "filename_prefix", `test_${format.toLowerCase()}`);
            set(node, "output_folder", "save-image-validation");
            assert(!node.widgets.some(w => ["save_prompt", "prompt_text"].includes(w.name)), "Prompt must only be a socket");
            text.connect(0, node, node.findInputSlot("prompt_text"));
            source.connect(0, node, 0);
            assert(Boolean(node.widgets.find(w => w.name === "png_compression").hidden) === (format !== "PNG"), "PNG visibility");
            assert(Boolean(node.widgets.find(w => w.name === "jpeg_quality").hidden) === (format !== "JPEG"), "JPEG visibility");
        }
        const workflow = JSON.parse(JSON.stringify(app.graph.serialize()));
        await app.loadGraphData(workflow);
        for (const node of app.graph._nodes.filter(n => n.type === "XavierSaveImage")) {
            const format = node.widgets.find(w => w.name === "format").value;
            assert(Boolean(node.widgets.find(w => w.name === "png_compression").hidden) === (format !== "PNG"), "Reload visibility");
            assert(node.widgets.find(w => w.name === "output_folder").value === "save-image-validation", "Reload folder");
            assert(!node.widgets.some(w => ["save_prompt", "prompt_text"].includes(w.name)), "Reload must not add prompt widgets");
            assert(node.inputs.find(input => input.name === "prompt_text")?.link != null, "Reload prompt link");
        }
        const saveNodes = app.graph._nodes.filter(n => n.type === "XavierSaveImage");
        // Check serialization without a link too, then restore the connection.
        const first = saveNodes[0];
        first.disconnectInput(first.findInputSlot("prompt_text"));
        const disconnected = await app.graphToPrompt();
        assert(!("prompt_text" in disconnected.output[first.id].inputs), "Unconnected prompt must be absent from execution");
        const restoredText = app.graph._nodes.find(n => n.type === "PrimitiveStringMultiline");
        restoredText.connect(0, first, first.findInputSlot("prompt_text"));
        const prompt = await app.graphToPrompt();
        const queue = await (await fetch("/queue")).json();
        assert(!queue.queue_running.length && !queue.queue_pending.length, "Queue is busy");
        await app.queuePrompt(0, 1);
        return { workflow, api: prompt.output, controls: true, reload: true, queued: true };
    });
}
