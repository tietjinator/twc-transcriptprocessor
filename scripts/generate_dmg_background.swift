import AppKit

guard CommandLine.arguments.count >= 2 else {
    fputs("Usage: generate_dmg_background.swift <output_png_path>\n", stderr)
    exit(1)
}

let outputPath = CommandLine.arguments[1]
let width = 680
let height = 420
let size = NSSize(width: width, height: height)

guard let rep = NSBitmapImageRep(
    bitmapDataPlanes: nil,
    pixelsWide: width,
    pixelsHigh: height,
    bitsPerSample: 8,
    samplesPerPixel: 4,
    hasAlpha: true,
    isPlanar: false,
    colorSpaceName: .deviceRGB,
    bytesPerRow: 0,
    bitsPerPixel: 0
) else {
    fputs("Failed to create bitmap context\n", stderr)
    exit(1)
}

NSGraphicsContext.saveGraphicsState()
guard let ctx = NSGraphicsContext(bitmapImageRep: rep) else {
    fputs("Failed to create graphics context\n", stderr)
    exit(1)
}
NSGraphicsContext.current = ctx

let rect = NSRect(origin: .zero, size: size)

let bgTop = NSColor(calibratedRed: 0.95, green: 0.96, blue: 0.99, alpha: 1.0)
let bgBottom = NSColor(calibratedRed: 0.90, green: 0.93, blue: 0.98, alpha: 1.0)
let gradient = NSGradient(starting: bgTop, ending: bgBottom)!
gradient.draw(in: rect, angle: -90)

let arrowColor = NSColor(calibratedRed: 0.05, green: 0.45, blue: 0.90, alpha: 0.55)
arrowColor.setFill()

let centerY: CGFloat = 210
let startX: CGFloat = 250
let endX: CGFloat = 430
let shaftHeight: CGFloat = 16
let headSize: CGFloat = 34

let shaftRect = NSRect(x: startX, y: centerY - shaftHeight / 2, width: endX - startX - headSize, height: shaftHeight)
NSBezierPath(roundedRect: shaftRect, xRadius: shaftHeight / 2, yRadius: shaftHeight / 2).fill()

let head = NSBezierPath()
head.move(to: NSPoint(x: endX - headSize, y: centerY - headSize / 2))
head.line(to: NSPoint(x: endX, y: centerY))
head.line(to: NSPoint(x: endX - headSize, y: centerY + headSize / 2))
head.close()
head.fill()

let text = "Drag Transcript Processor to Applications"
let paragraph = NSMutableParagraphStyle()
paragraph.alignment = .center

let attrs: [NSAttributedString.Key: Any] = [
    .font: NSFont.systemFont(ofSize: 28, weight: .semibold),
    .foregroundColor: NSColor(calibratedWhite: 0.2, alpha: 0.95),
    .paragraphStyle: paragraph
]

let textRect = NSRect(x: 40, y: 300, width: size.width - 80, height: 44)
text.draw(in: textRect, withAttributes: attrs)

NSGraphicsContext.restoreGraphicsState()

let pngData = rep.representation(using: .png, properties: [:])
if let pngData {
    do {
        try pngData.write(to: URL(fileURLWithPath: outputPath))
    } catch {
        fputs("Failed to write PNG: \(error)\n", stderr)
        exit(1)
    }
} else {
    fputs("Failed to encode PNG\n", stderr)
    exit(1)
}
