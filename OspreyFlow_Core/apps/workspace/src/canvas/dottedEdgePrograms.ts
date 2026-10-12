// The dotted edge programs (ADR-081). A probabilistic link is always drawn dotted, a direct one
// solid, and Sigma 3's stock edge programs draw only solid lines (checked 3 October 2026 against
// the installed 3.0.3: no dash or dot option, and the plain line program is one pixel wide whatever
// the edge's size). So the Glass carries two small programs of its own, both thin subclasses of
// Sigma's own "clamped" shaft, the one `EdgeArrowProgram` is built from:
//
// - `DottedEdgeProgram`: a dotted shaft with no arrowhead, for an undirected type such as `SAME_AS`.
// - `DottedArrowProgram`: the same dotted shaft, shortened at the target exactly as the stock arrow's
//   is, plus Sigma's own arrowhead, for a directed probabilistic type.
//
// Only two things differ from Sigma's shaft: the vertex shader also reports how far along the edge
// each vertex is, in screen pixels, and the fragment shader throws away the gaps. The pattern is in
// screen pixels, not graph units, so it stays the same size at every zoom. In picking mode (the
// pass that tells the canvas which edge is under the pointer) nothing is thrown away, so a gap in a
// dotted link can still be pointed at and selected.
import {
  createEdgeArrowHeadProgram,
  createEdgeArrowProgram,
  createEdgeClampedProgram,
  createEdgeCompoundProgram,
  type EdgeArrowProgram,
  type EdgeLineProgram,
} from "sigma/rendering";
import type { RenderParams } from "sigma/types";

import { DASH_LENGTH_PX, DASH_PERIOD_PX, DOT_LENGTH_PX, DOT_PERIOD_PX } from "./provenancePatterns";

export { DASH_LENGTH_PX, DASH_PERIOD_PX, DOT_LENGTH_PX, DOT_PERIOD_PX };

/** Sigma's own arrowhead is 2.5 times the line's width long and twice as wide, which at one pixel is
 * smaller than a 20px node's edge can show (ADR-097 step 2). These make it 6 by 5 at one pixel. */
export const ARROW_HEAD_OPTIONS = { lengthToThicknessRatio: 6, widenessToThicknessRatio: 5 } as const;

// language=GLSL
const VERTEX_SHADER = /*glsl*/ `
attribute vec4 a_id;
attribute vec4 a_color;
attribute vec2 a_normal;
attribute float a_normalCoef;
attribute vec2 a_positionStart;
attribute vec2 a_positionEnd;
attribute float a_positionCoef;
attribute float a_radius;
attribute float a_radiusCoef;

uniform mat3 u_matrix;
uniform float u_zoomRatio;
uniform float u_sizeRatio;
uniform float u_pixelRatio;
uniform float u_correctionRatio;
uniform float u_minEdgeThickness;
uniform float u_lengthToThicknessRatio;
uniform float u_feather;
uniform vec2 u_resolution;

varying vec4 v_color;
varying vec2 v_normal;
varying float v_thickness;
varying float v_feather;
varying float v_along;

const float bias = 255.0 / 254.0;

void main() {
  float minThickness = u_minEdgeThickness;

  float radius = a_radius * a_radiusCoef;
  vec2 normal = a_normal * a_normalCoef;
  vec2 position = a_positionStart * (1.0 - a_positionCoef) + a_positionEnd * a_positionCoef;

  float normalLength = length(normal);
  vec2 unitNormal = normal / normalLength;

  float pixelsThickness = max(normalLength, minThickness * u_sizeRatio);
  float webGLThickness = pixelsThickness * u_correctionRatio / u_sizeRatio;

  // Leave room for the arrowhead (a radius of 0 leaves none, so a plain dotted line runs the whole way).
  float direction = sign(radius);
  float webGLNodeRadius = direction * radius * 2.0 * u_correctionRatio / u_sizeRatio;
  float webGLArrowHeadLength = webGLThickness * u_lengthToThicknessRatio * 2.0;

  vec2 compensationVector = vec2(-direction * unitNormal.y, direction * unitNormal.x) * (webGLNodeRadius + webGLArrowHeadLength);

  gl_Position = vec4((u_matrix * vec3(position + unitNormal * webGLThickness + compensationVector, 1)).xy, 0, 1);

  // How far along the edge this vertex is, in screen pixels from its source end.
  vec2 startClip = (u_matrix * vec3(a_positionStart, 1)).xy;
  vec2 endClip = (u_matrix * vec3(a_positionEnd, 1)).xy;
  float lengthPx = length((endClip - startClip) * 0.5 * u_resolution);
  v_along = a_positionCoef * lengthPx;

  v_thickness = webGLThickness / u_zoomRatio;
  v_normal = unitNormal;
  v_feather = u_feather * u_correctionRatio / u_zoomRatio / u_pixelRatio * 2.0;

  #ifdef PICKING_MODE
  v_color = a_id;
  #else
  v_color = a_color;
  #endif

  v_color.a *= bias;
}
`;

// language=GLSL
const fragmentShader = (on: number, period: number) => /*glsl*/ `
precision highp float;

varying vec4 v_color;
varying vec2 v_normal;
varying float v_thickness;
varying float v_feather;
varying float v_along;

const vec4 transparent = vec4(0.0, 0.0, 0.0, 0.0);
const float DOT = ${on.toFixed(1)};
const float PERIOD = ${period.toFixed(1)};

void main(void) {
  #ifdef PICKING_MODE
  gl_FragColor = v_color;
  #else
  if (mod(v_along, PERIOD) > DOT) discard;

  float dist = length(v_normal) * v_thickness;
  float t = smoothstep(v_thickness - v_feather, v_thickness, dist);
  gl_FragColor = mix(v_color, transparent, t);
  #endif
}
`;

/** The one thing a subclass needs beyond Sigma's own shaft: the canvas size, for the pattern. */
interface ShaftDefinition {
  VERTEX_SHADER_SOURCE: string;
  FRAGMENT_SHADER_SOURCE: string;
  UNIFORMS: string[];
}
interface ShaftContext {
  gl: WebGLRenderingContext;
  uniformLocations: Record<string, WebGLUniformLocation | null>;
}

function dottedShaft(
  options: { lengthToThicknessRatio: number },
  noArrowRoom: boolean,
  pattern: { on: number; period: number } = { on: DOT_LENGTH_PX, period: DOT_PERIOD_PX },
) {
  const Base = createEdgeClampedProgram(options) as unknown as new (...args: unknown[]) => {
    getDefinition(): ShaftDefinition;
    setUniforms(params: RenderParams, context: ShaftContext): void;
    processVisibleItem(
      edgeIndex: number,
      startIndex: number,
      sourceData: unknown,
      targetData: unknown,
      data: unknown,
    ): void;
    array: Float32Array;
  };
  class DottedShaft extends Base {
    getDefinition() {
      const definition = super.getDefinition();
      return {
        ...definition,
        VERTEX_SHADER_SOURCE: VERTEX_SHADER,
        FRAGMENT_SHADER_SOURCE: fragmentShader(pattern.on, pattern.period),
        UNIFORMS: [...definition.UNIFORMS, "u_resolution"],
      };
    }
    setUniforms(params: RenderParams, context: ShaftContext) {
      super.setUniforms(params, context);
      context.gl.uniform2f(context.uniformLocations.u_resolution ?? null, params.width, params.height);
    }
    processVisibleItem(
      edgeIndex: number,
      startIndex: number,
      sourceData: unknown,
      targetData: unknown,
      data: unknown,
    ) {
      super.processVisibleItem(edgeIndex, startIndex, sourceData, targetData, data);
      // Sigma writes the target node's size as the room to leave; a plain dotted line leaves none.
      if (noArrowRoom) this.array[startIndex + 8] = 0;
    }
  }
  return DottedShaft;
}

/** A dotted line with no arrowhead: for an undirected probabilistic type. */
// Typed as the stock programs they stand beside, which is the type Sigma's settings accept.
export const DottedEdgeProgram = dottedShaft({ lengthToThicknessRatio: 0 }, true) as unknown as typeof EdgeLineProgram;

/** A dotted line with the arrowhead: for a directed probabilistic type. */
export const DottedArrowProgram = createEdgeCompoundProgram([
  dottedShaft({ lengthToThicknessRatio: ARROW_HEAD_OPTIONS.lengthToThicknessRatio }, false) as never,
  createEdgeArrowHeadProgram(ARROW_HEAD_OPTIONS) as never,
]) as unknown as typeof EdgeArrowProgram;

const DASH = { on: DASH_LENGTH_PX, period: DASH_PERIOD_PX };

/** A dashed line with no arrowhead: an inferred link of an undirected type (ADR-097 step 2). */
export const DashedEdgeProgram = dottedShaft({ lengthToThicknessRatio: 0 }, true, DASH) as unknown as typeof EdgeLineProgram;

/** A dashed line with the arrowhead: an inferred link of a directed type. */
export const DashedArrowProgram = createEdgeCompoundProgram([
  dottedShaft({ lengthToThicknessRatio: ARROW_HEAD_OPTIONS.lengthToThicknessRatio }, false, DASH) as never,
  createEdgeArrowHeadProgram(ARROW_HEAD_OPTIONS) as never,
]) as unknown as typeof EdgeArrowProgram;

/** A solid line with the arrowhead, at the size above. */
export const SolidArrowProgram = createEdgeArrowProgram(ARROW_HEAD_OPTIONS) as unknown as typeof EdgeArrowProgram;
