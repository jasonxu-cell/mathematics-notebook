import AppKit
import Foundation

let output = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
for size in [16, 32, 64, 128, 256, 512, 1024] {
    let image = NSImage(size: NSSize(width: size, height: size))
    image.lockFocus()
    let scale = CGFloat(size) / 1024
    let rect = NSRect(x: 56 * scale, y: 56 * scale, width: 912 * scale, height: 912 * scale)
    NSColor(calibratedRed: 0.89, green: 0.43, blue: 0.24, alpha: 1).setFill()
    NSBezierPath(roundedRect: rect, xRadius: 214 * scale, yRadius: 214 * scale).fill()
    let attributes: [NSAttributedString.Key: Any] = [
        .font: NSFont(name: "Georgia-Italic", size: 720 * scale) ?? NSFont.systemFont(ofSize: 680 * scale),
        .foregroundColor: NSColor(calibratedRed: 1, green: 0.98, blue: 0.93, alpha: 1),
    ]
    let text = NSAttributedString(string: "m", attributes: attributes)
    let measured = text.size()
    text.draw(at: NSPoint(x: (CGFloat(size) - measured.width) / 2 - 22 * scale, y: (CGFloat(size) - measured.height) / 2 + 44 * scale))
    image.unlockFocus()
    let bitmap = NSBitmapImageRep(data: image.tiffRepresentation!)!
    let png = bitmap.representation(using: .png, properties: [:])!
    for (name, width) in [("icon_16x16.png", 16), ("icon_16x16@2x.png", 32), ("icon_32x32.png", 32), ("icon_32x32@2x.png", 64), ("icon_128x128.png", 128), ("icon_128x128@2x.png", 256), ("icon_256x256.png", 256), ("icon_256x256@2x.png", 512), ("icon_512x512.png", 512), ("icon_512x512@2x.png", 1024)] {
        if width == size { try png.write(to: output.appendingPathComponent(name)) }
    }
}
