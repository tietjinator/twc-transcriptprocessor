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

let glowLeft = NSColor(calibratedRed: 0.75, green: 0.86, blue: 1.0, alpha: 0.16)
let glowRight = NSColor(calibratedRed: 0.62, green: 0.78, blue: 1.0, alpha: 0.14)
glowLeft.setFill()
NSBezierPath(ovalIn: NSRect(x: 76, y: 86, width: 212, height: 212)).fill()
glowRight.setFill()
NSBezierPath(ovalIn: NSRect(x: 392, y: 86, width: 212, height: 212)).fill()

let arrowGlow = NSColor(calibratedRed: 0.12, green: 0.50, blue: 0.92, alpha: 0.20)
let arrowColor = NSColor(calibratedRed: 0.10, green: 0.48, blue: 0.90, alpha: 0.82)

let centerY: CGFloat = 210
let shaftStart: CGFloat = 250
let shaftEnd: CGFloat = 412
let headTip: CGFloat = 438

let arrowShadow = NSBezierPath()
arrowShadow.lineCapStyle = .round
arrowShadow.lineJoinStyle = .round
arrowShadow.lineWidth = 22
arrowShadow.move(to: NSPoint(x: shaftStart, y: centerY))
arrowShadow.line(to: NSPoint(x: shaftEnd, y: centerY))
arrowGlow.setStroke()
arrowShadow.stroke()

let arrow = NSBezierPath()
arrow.lineCapStyle = .round
arrow.lineJoinStyle = .round
arrow.lineWidth = 14
arrow.move(to: NSPoint(x: shaftStart, y: centerY))
arrow.line(to: NSPoint(x: shaftEnd, y: centerY))
arrow.move(to: NSPoint(x: shaftEnd - 18, y: centerY + 20))
arrow.line(to: NSPoint(x: headTip, y: centerY))
arrow.line(to: NSPoint(x: shaftEnd - 18, y: centerY - 20))
arrowColor.setStroke()
arrow.stroke()

let applicationsIcon = NSWorkspace.shared.icon(forFile: "/Applications")
applicationsIcon.size = NSSize(width: 128, height: 128)
applicationsIcon.draw(
    in: NSRect(x: 438, y: 102, width: 128, height: 128),
    from: .zero,
    operation: .sourceOver,
    fraction: 0.30
)

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
