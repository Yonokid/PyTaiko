#version 330
in vec2 fragTexCoord;
in vec4 fragColor;
uniform sampler2D texture0;
uniform vec4 colDiffuse;
uniform vec2 textureSize;
uniform float outlineSize;
uniform vec4 outlineColor;
uniform float alpha;
uniform float smoothness = 1.0;
out vec4 finalColor;

void main()
{
    vec4 texel = texture(texture0, fragTexCoord);
    vec2 texelScale = vec2(outlineSize/textureSize.x, outlineSize/textureSize.y);

    float outline = 0.0;
    int ringSamples = 16;
    int rings = 2;
    for(int ring = 1; ring <= rings; ring++) {
        float ringRadius = float(ring) / float(rings);
        for(int i = 0; i < ringSamples; i++) {
            float angle = 2.0 * 3.14159 * float(i) / float(ringSamples);
            vec2 offset = vec2(cos(angle), sin(angle)) * texelScale * ringRadius;
            outline += texture(texture0, fragTexCoord + offset).a / float(rings);
        }
    }
    outline = min(outline, 1.0);
    outline = smoothstep(0.3, 0.7, outline);

    float edgeStart = 0.5 - smoothness * 0.3;
    float edgeEnd = 0.5 + smoothness * 0.3;
    float textAlpha = smoothstep(edgeStart, edgeEnd, texel.a);
    vec3 color = mix(outlineColor.rgb, texel.rgb, textAlpha);
    float combinedAlpha = mix(outline * outlineColor.a, texel.a, textAlpha);

    finalColor = vec4(color, combinedAlpha * alpha);
}
