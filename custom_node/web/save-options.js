import { app } from "../../scripts/app.js";

const hiddenWidgets = new WeakMap();

function updateControls(node, resize = false) {
    const format = node.widgets?.find(widget => widget.name === "format")?.value;
    const dynamic = node.inputs?.some(input => input.name === "format" && input.link != null);
    const oldHeight = node.computeSize()[1];
    let changed = false;
    for (const widget of node.widgets ?? []) {
        if (!["png_compression", "jpeg_quality"].includes(widget.name)) continue;
        const visible = dynamic || (widget.name === "png_compression" ? format === "PNG" : format === "JPEG");
        const previous = hiddenWidgets.get(widget);
        if (!visible && !previous) {
            hiddenWidgets.set(widget, { hidden: widget.hidden, optionsHidden: widget.options?.hidden });
            widget.hidden = true;
            widget.options = { ...widget.options, hidden: true };
            changed = true;
        } else if (visible && previous) {
            widget.hidden = previous.hidden ?? false;
            widget.options.hidden = previous.optionsHidden ?? false;
            hiddenWidgets.delete(widget);
            changed = true;
        }
    }
    if (changed && resize) {
        const height = node.computeSize()[1];
        node.setSize([node.size[0], Math.max(height, node.size[1] + height - oldHeight)]);
    }
    if (changed) node.setDirtyCanvas(true, true);
}

app.registerExtension({
    name: "XavierSaveImage.FormatOptions",
    beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "XavierSaveImage") return;
        const created = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = created?.apply(this, arguments);
            const format = this.widgets?.find(widget => widget.name === "format");
            if (format) {
                const callback = format.callback;
                const node = this;
                format.callback = function () {
                    const value = callback?.apply(this, arguments);
                    updateControls(node, true);
                    return value;
                };
            }
            updateControls(this);
            return result;
        };
        const configure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            const result = configure?.apply(this, arguments);
            updateControls(this);
            return result;
        };
        const connections = nodeType.prototype.onConnectionsChange;
        nodeType.prototype.onConnectionsChange = function (type, slot) {
            const result = connections?.apply(this, arguments);
            if (type === globalThis.LiteGraph.INPUT && this.inputs?.[slot]?.name === "format") {
                updateControls(this, true);
            }
            return result;
        };
    },
});
