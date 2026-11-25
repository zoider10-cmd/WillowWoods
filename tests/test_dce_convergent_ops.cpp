// (HeyListen bdd56f2a, their issue 97: black leaves) Dead code elimination keeps the warp-wide operations (VOTE, ballot,
// shuffles) even when nothing reads their result: they are convergence points of the guest program, and the ballot and shuffle
// that follow a vote depend on the lanes having met there. In HeyListen their pseudo-operation fold left a VoteAny without a
// reader (R2P mask 0x40); here FoldSelect on an immediate condition does the same: Select(false, VoteAny(true), x) keeps x.
// Runs the real ConstantPropagationPass and DeadCodeEliminationPass. tests/test_dce_convergent_ops.py builds it.
#include <cstdio>
#include <cstdlib>
#include <exception>

#include "shader_recompiler/environment.h"
#include "shader_recompiler/frontend/ir/basic_block.h"
#include "shader_recompiler/frontend/ir/ir_emitter.h"
#include "shader_recompiler/frontend/ir/program.h"
#include "shader_recompiler/ir_opt/passes.h"

using namespace Shader;

namespace {
class Env final : public Environment {
public:
    u64 ReadInstruction(u32) override { return 0; }
    u32 ReadCbufValue(u32, u32) override { return 0; }
    TextureType ReadTextureType(u32) override { return {}; }
    TexturePixelFormat ReadTexturePixelFormat(u32) override { return {}; }
    bool IsTexturePixelFormatInteger(u32) override { return false; }
    u32 ReadViewportTransformState() override { return 0; }
    u32 TextureBoundBuffer() const override { return 0; }
    u32 LocalMemorySize() const override { return 0; }
    u32 SharedMemorySize() const override { return 0; }
    std::array<u32, 3> WorkgroupSize() const override { return {1, 1, 1}; }
    bool HasHLEMacroState() const override { return false; }
    std::optional<ReplaceConstant> GetReplaceConstBuffer(u32, u32) override { return std::nullopt; }
    void Dump(u64, u64) override {}
};

int count(IR::Block& block, IR::Opcode op) {
    int n{};
    for (const IR::Inst& inst : block) {
        n += inst.GetOpcode() == op ? 1 : 0;
    }
    return n;
}
} // namespace

int main() {
    int bad{};
    {   // a vote left without a reader by the constant fold of a Select on an immediate condition
        ObjectPool<IR::Inst> inst_pool;
        ObjectPool<IR::Block> block_pool;
        IR::Program program{};
        IR::Block* const block{block_pool.Create(inst_pool)};
        program.blocks.push_back(block);
        program.post_order_blocks.push_back(block);
        IR::IREmitter ir{*block};
        const IR::U1 vote{ir.VoteAny(ir.Imm1(true))};
        const IR::U32 src{ir.GetCbuf(ir.Imm32(0), ir.Imm32(0x20))};
        const IR::U1 src_bit{ir.LogicalNot(ir.GetZeroFromOp(ir.BitFieldExtract(src, ir.Imm32(6), ir.Imm32(1), false)))};
        const IR::U1 p6{IR::U1{ir.Select(ir.Imm1(false), vote, src_bit)}};
        ir.ConditionRef(p6);
        Env env;
        try {
            Optimization::ConstantPropagationPass(env, program);
            Optimization::DeadCodeEliminationPass(program);
        } catch (const std::exception& e) {
            std::printf("FAIL: pass threw %s\n", e.what());
            return 1;
        }
        if (count(*block, IR::Opcode::VoteAny) != 1) {
            std::printf("FAIL: the VoteAny the fold left without a reader was removed (%d left)\n",
                        count(*block, IR::Opcode::VoteAny));
            ++bad;
        }
    }
    {   // every warp-wide operation survives with no reader
        ObjectPool<IR::Inst> inst_pool;
        ObjectPool<IR::Block> block_pool;
        IR::Program program{};
        IR::Block* const block{block_pool.Create(inst_pool)};
        program.blocks.push_back(block);
        program.post_order_blocks.push_back(block);
        IR::IREmitter ir{*block};
        const IR::U1 t{ir.Imm1(true)};
        const IR::U32 x{ir.GetCbuf(ir.Imm32(0), ir.Imm32(0x20))};
        (void)ir.VoteAll(t); (void)ir.VoteAny(t); (void)ir.VoteEqual(t); (void)ir.SubgroupBallot(t);
        (void)ir.ShuffleIndex(x, ir.Imm32(0), ir.Imm32(31), ir.Imm32(0));
        (void)ir.ShuffleUp(x, ir.Imm32(1), ir.Imm32(0), ir.Imm32(0));
        (void)ir.ShuffleDown(x, ir.Imm32(1), ir.Imm32(31), ir.Imm32(0));
        (void)ir.ShuffleButterfly(x, ir.Imm32(1), ir.Imm32(31), ir.Imm32(0));
        Optimization::DeadCodeEliminationPass(program);
        const IR::Opcode ops[] = {IR::Opcode::VoteAll, IR::Opcode::VoteAny, IR::Opcode::VoteEqual, IR::Opcode::SubgroupBallot,
                                  IR::Opcode::ShuffleIndex, IR::Opcode::ShuffleUp, IR::Opcode::ShuffleDown,
                                  IR::Opcode::ShuffleButterfly};
        for (IR::Opcode op : ops) {
            if (count(*block, op) != 1) {
                std::printf("FAIL: opcode %d removed with no reader\n", static_cast<int>(op));
                ++bad;
            }
        }
    }
    std::printf(bad ? "FAILED\n" : "ok: a vote the fold left without a reader and the other warp-wide operations survive dead code elimination\n");
    return bad ? 1 : 0;
}
